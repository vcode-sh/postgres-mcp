# PostgreSQL 17 & 18 Support Plan

**Status: TODO** — Deep audit complete. Ready for implementation.

---

## Current State

Server supports **PG 12–16**. Test matrix: `postgres:12`, `postgres:15`, `postgres:16`.

Version detection: `extension_utils.py:34` (`get_postgres_version()`) returns major int.
Version gating: `extension_utils.py:69` (`check_postgres_version_requirement()`).
Replication version: `replication_calc.py:155` (`_get_server_version()`) returns `server_version_num` int.

---

## Phase 1: Compatibility Fixes (MUST-DO)

These changes prevent runtime errors on PG 17/18.

### 1.1 Test matrix: add PG 17 + PG 18

**Files:**
- `tests/conftest.py:20` — add `"postgres:17"`, `"postgres:18"` to params
- `tests/Dockerfile.postgres-hypopg:1` — verify HypoPG builds on PG 17/18 (HypoPG 1.4.1+ supports PG 17; confirm PG 18)

```python
# conftest.py:20
@pytest.fixture(scope="class", params=["postgres:12", "postgres:15", "postgres:16", "postgres:17", "postgres:18"])
```

### 1.2 `pg_stat_statements` column renames (PG 17)

PG 17 renamed:
- `blk_read_time` → `shared_blk_read_time`
- `blk_write_time` → `shared_blk_write_time`

**Current impact**: The existing queries in `top_queries_calc.py` do NOT reference `blk_read_time`/`blk_write_time` directly — they use `shared_blks_hit`, `shared_blks_read`, `shared_blks_dirtied`, and the version-gated timing columns. **No breakage here**, but we need a PG 17+ branch in `_get_pg_stat_statements_columns()` to expose the new columns (see Phase 3).

### 1.3 `index_opt_base.py:421` — hardcoded `total_exec_time` without version gate

**BUG (existing, not PG 17/18 specific):** `_get_query_stats_direct()` uses `total_exec_time` which doesn't exist on PG 12 (it's `total_time` there). This is already broken on PG 12.

**Fix:** Use `_get_pg_stat_statements_columns()` from `top_queries_calc.py` or extract a shared helper. The column helper should be moved to a shared location (e.g. `sql/pg_compat.py` or `top_queries/columns.py`).

```python
# index_opt_base.py:421 — currently:
query = """
SELECT queryid, query, calls, total_exec_time/calls as avg_exec_time
FROM pg_stat_statements
WHERE calls >= {} AND total_exec_time/calls >= {} ORDER BY total_exec_time DESC LIMIT {}
"""

# fix: use version-appropriate column name
pg_version = await get_postgres_version(self.sql_driver)
cols = _get_pg_stat_statements_columns(pg_version)
query = f"""
SELECT queryid, query, calls, {cols.total_time}/calls as avg_exec_time
FROM pg_stat_statements
WHERE calls >= {{}} AND {cols.total_time}/calls >= {{}} ORDER BY {cols.total_time} DESC LIMIT {{}}
"""
```

### 1.4 Verify `pglast` PG 17/18 syntax support

**File:** `pyproject.toml:11` — `pglast==7.11`

`pglast` 7.x is based on PG 17's `libpg_query`. Verify:
- PG 17 syntax: `JSON_TABLE`, `MERGE ... RETURNING`, `merge_action()` — should parse
- PG 18 syntax: `RETURNING OLD/NEW`, temporal `WITHOUT OVERLAPS`, virtual generated columns — may need pglast 8.x

**Action:** Run `pglast` parse tests against PG 18 syntax. If it fails, check for a newer version or pin to a version that supports PG 18 grammar. This is critical because `SafeSqlDriver` uses `pglast` to validate all SQL in restricted mode.

### 1.5 Docker data directory (PG 18)

PG 18 Docker images changed data dir to `/var/lib/postgresql/18/data`. The `Dockerfile.postgres-hypopg` and `tests/utils.py` should not be affected (they use Docker entrypoint defaults), but verify during integration testing.

---

## Phase 2: Enhanced EXPLAIN (HIGH VALUE)

### 2.1 EXPLAIN MEMORY option (PG 17+)

**File:** `explain/explain_plan.py:153-183`

PG 17 added `EXPLAIN (MEMORY)` — reports planner memory usage.

**Change:** Add optional `memory` parameter to `explain()` and `_run_explain_query()`. Gate behind `pg_version >= 17`.

```python
# explain_plan.py:_run_explain_query
if memory and pg_version >= 17:
    explain_options.append("MEMORY")
```

**Also update:** `tools/query_tools.py` — add `include_memory: bool = False` parameter to the `postgres_explain_query` tool.

### 2.2 EXPLAIN SERIALIZE option (PG 17+)

PG 17 added `EXPLAIN (ANALYZE, SERIALIZE [TEXT|BINARY])` — reports serialization cost.

**Change:** Add optional `serialize` parameter. Only valid when `analyze=True`. Gate behind `pg_version >= 17`.

```python
if serialize and analyze and pg_version >= 17:
    explain_options.append(f"SERIALIZE {serialize.upper()}")
```

### 2.3 BUFFERS auto-included with ANALYZE (PG 18+)

PG 18 changed behavior: `EXPLAIN ANALYZE` automatically includes `BUFFERS` output.

**Change:** This is informational — no code change strictly required (BUFFERS is not harmful to include explicitly). But if we add explicit BUFFERS in the future, we should skip it on PG 18+ since it's already included.

### 2.4 Pass PG version to ExplainPlanTool

Currently `ExplainPlanTool.__init__` only receives `sql_driver`. The version must be fetched async. Two options:
- A) Call `get_postgres_version()` inside `_run_explain_query()` (adds an extra query per call, but version is cached globally)
- B) Store version at init time via an async factory method

**Recommendation:** Option A — the global cache in `extension_utils.py:14` means only the first call hits the DB.

---

## Phase 3: Enhanced Top Queries (HIGH VALUE)

### 3.1 New `pg_stat_statements` columns (PG 17)

PG 17 added:
- `stats_since` — when the entry was created (useful for time-window context)
- `minmax_stats_since` — last min/max reset
- `local_blk_read_time` / `local_blk_write_time` — local (temp table) I/O timing

**File:** `top_queries/top_queries_calc.py:44-79`

**Change:** Add PG 17+ branch to `_get_pg_stat_statements_columns()`. Extend `PgStatStatementsColumns` dataclass:

```python
@dataclass
class PgStatStatementsColumns:
    total_time: str
    mean_time: str
    stddev_time: str
    wal_bytes_select: str
    wal_bytes_frac: str
    stats_since_select: str        # NEW: "" for <17, "stats_since" for 17+
    local_blk_timing_select: str   # NEW: "" for <17, column exprs for 17+
```

### 3.2 New `pg_stat_statements` columns (PG 18)

PG 18 added:
- `parallel_workers_to_launch` — planned parallel workers
- `parallel_workers_launched` — actual parallel workers
- `wal_buffers_full` — full WAL buffer count

**Change:** Add PG 18+ branch. Include in resource queries output for parallel query analysis.

### 3.3 Extract shared column helper

`_get_pg_stat_statements_columns()` is used in `top_queries_calc.py` but duplicated (hardcoded) in `index_opt_base.py:421`. Extract to a shared module.

**New file:** `src/postgres_mcp/sql/pg_compat.py` — shared PG version compatibility helpers.
Move `PgStatStatementsColumns` and `_get_pg_stat_statements_columns()` there.

---

## Phase 4: Enhanced Health Checks (HIGH VALUE)

### 4.1 Replication slots — new columns (PG 17+)

PG 17 added to `pg_replication_slots`:
- `invalidation_reason` — why a slot is invalid
- `inactive_since` — how long slot has been inactive
- `failover` — slot configured for failover sync
- `synced` — slot synchronized to standby

**File:** `database_health/replication_calc.py:120-126`

**Change:** On PG 17+, query additional columns and include in health report:

```python
if pg_version >= 17:
    query = """SELECT slot_name, database, active,
                      invalidation_reason, inactive_since, failover, synced
               FROM pg_replication_slots"""
else:
    query = """SELECT slot_name, database, active FROM pg_replication_slots"""
```

Update `ReplicationSlot` dataclass with optional new fields.

### 4.2 Replication — idle slot timeout (PG 18+)

PG 18 added `idle_replication_slot_timeout` parameter. Health check can warn about slots approaching timeout.

### 4.3 Connection health — pg_wait_events join (PG 17+)

PG 17 added `pg_wait_events` view for human-readable wait event descriptions.

**File:** `database_health/connection_health_calc.py:59-76`

**Change:** On PG 17+, enhance idle connection query to include wait event info:

```sql
SELECT COUNT(*) as count,
       we.wait_event_type, we.wait_event_name, we.description
FROM pg_stat_activity sa
LEFT JOIN pg_wait_events we ON sa.wait_event_type = we.type AND sa.wait_event = we.name
WHERE state = 'idle in transaction'
GROUP BY we.wait_event_type, we.wait_event_name, we.description
```

### 4.4 Vacuum health — timing columns (PG 18+)

PG 18 added to `pg_stat_user_tables`:
- `total_vacuum_time` — microseconds spent in manual vacuums
- `total_autovacuum_time` — microseconds in autovacuums
- `total_analyze_time` — microseconds in manual analyzes
- `total_autoanalyze_time` — microseconds in auto-analyzes

**File:** `database_health/vacuum_health_calc.py:87-102`

**Change:** On PG 18+, include timing data in `_get_vacuum_stats()`:

```sql
-- PG 18+
SELECT relname, last_vacuum, last_autovacuum,
       total_vacuum_time, total_autovacuum_time,
       total_analyze_time, total_autoanalyze_time
FROM pg_stat_user_tables
```

### 4.5 New checkpoint health calculator (PG 17+)

PG 17 added `pg_stat_checkpointer` (split from `pg_stat_bgwriter`).
PG 18 added `num_done` and `slru_written` columns.

**New file:** `database_health/checkpoint_health_calc.py`

Query `pg_stat_checkpointer` for:
- `num_timed` / `num_requested` — checkpoint frequency
- `write_time` / `sync_time` — checkpoint duration
- `buffers_written` — checkpoint throughput

Register in `DatabaseHealthTool` orchestrator.

### 4.6 I/O monitoring via pg_stat_io (PG 18+)

PG 18 enhanced `pg_stat_io` with byte-level columns (`read_bytes`, `write_bytes`, `extend_bytes`) and moved WAL I/O tracking here from `pg_stat_wal`.

**Opportunity:** New `io_health_calc.py` for comprehensive I/O health monitoring. Lower priority — adds a new tool dimension.

---

## Phase 5: Index Intelligence

### 5.1 B-tree skip scan awareness (PG 18+)

PG 18 added B-tree skip scan: multicolumn indexes work even without equality on leading columns.

**File:** `index/dta_calc.py`, `index/index_opt_base.py`

**Impact:** The DTA may over-recommend indexes for queries that would benefit from skip scan on existing indexes. On PG 18+, the optimizer will already handle these cases.

**Change:** When running on PG 18+, after generating hypothetical indexes, check if any recommended index is a prefix of an existing multicolumn index. If skip scan could handle the query, annotate the recommendation as "may not be needed with skip scan" or lower its priority.

### 5.2 EXPLAIN index lookup counts (PG 18+)

PG 18 EXPLAIN ANALYZE output includes index lookup counts.

**Change:** `ExplainPlanArtifact.from_json_data()` should handle the new fields without error. If the artifact model uses strict parsing, ensure it allows unknown keys.

---

## Phase 6: SafeSqlDriver Updates

### 6.1 New PG 17 functions to whitelist

**File:** `sql/safe_sql.py:122+` — `ALLOWED_FUNCTIONS` set

Add:
```python
# PG 17 JSON functions
"json_exists",
"json_query",
"json_value",
"json_scalar",
"json_serialize",
"json_table",  # Also a SQL keyword — verify pglast handling
"merge_action",
# PG 17 functions
"pg_sync_replication_slots",
"pg_available_wal_summaries",
"pg_wal_summary_contents",
```

### 6.2 New PG 18 functions to whitelist

Add:
```python
# PG 18 UUID functions
"uuidv4",
"uuidv7",
"uuid_extract_timestamp",
"uuid_extract_version",
# PG 18 array functions
"array_sort",
"array_reverse",
# PG 18 math functions
"gamma",
"lgamma",
# PG 18 string functions
"casefold",
# PG 18 binary/CRC functions
"crc32",
"crc32c",
# PG 18 monitoring
"pg_stat_get_backend_io",
"pg_stat_get_backend_wal",
"pg_stat_reset_backend_stats",
"pg_get_acl",
"pg_get_loaded_modules",
"pg_numa_available",
# PG 18 privilege functions
"has_largeobject_privilege",
```

### 6.3 `pglast` AST handling for new syntax

PG 17 introduced `JSON_TABLE` (used in FROM clauses). `pglast` 7.x (based on PG 17 grammar) should handle this.

PG 18 introduced:
- `RETURNING OLD/NEW` in UPDATE/DELETE/MERGE
- `WITHOUT OVERLAPS` in constraints
- Virtual generated columns

If `pglast` 7.x can't parse these, `SafeSqlDriver` will reject valid PG 18 SQL in restricted mode. Test and upgrade `pglast` as needed.

---

## Phase 7: Schema Inspection Updates

### 7.1 Virtual generated columns (PG 18+)

PG 18 defaults to `VIRTUAL` generated columns (previously `STORED`).

**File:** `tools/schema_tools.py:131-140` — `information_schema.columns` query

**Change:** On PG 18+, the `column_default` field may not show the generation expression for virtual columns. Consider querying `pg_attribute` + `pg_attrdef` directly, or add `generation_expression` and `is_generated` from `information_schema.columns` (available since PG 12):

```sql
SELECT column_name, data_type, is_nullable, column_default,
       is_generated, generation_expression
FROM information_schema.columns
WHERE table_schema = {} AND table_name = {}
ORDER BY ordinal_position
```

### 7.2 NOT ENFORCED constraints (PG 18+)

PG 18 added `NOT ENFORCED` for CHECK and FK constraints. The `pg_constraint.conforced` column indicates enforcement.

**File:** `database_health/constraint_health_calc.py:43-62`

The existing query filters `convalidated = 'f'` (not validated). On PG 18+, also consider `conforced` — a constraint that is `NOT ENFORCED` is different from one that is not validated.

---

## Implementation Order

| Priority | Phase | Items | Effort |
|----------|-------|-------|--------|
| **P0** | 1.1 | Test matrix expansion | S |
| **P0** | 1.3 | Fix `index_opt_base.py` PG 12 bug | S |
| **P0** | 1.4 | Verify pglast PG 18 support | M |
| **P1** | 3.3 | Extract shared column helper | S |
| **P1** | 2.1-2.2 | EXPLAIN MEMORY + SERIALIZE | M |
| **P1** | 3.1-3.2 | pg_stat_statements new columns | M |
| **P1** | 4.1 | Replication slots new columns | S |
| **P2** | 4.4 | Vacuum timing columns | S |
| **P2** | 4.3 | Connection wait events | M |
| **P2** | 6.1-6.2 | Function whitelist updates | S |
| **P2** | 4.5 | Checkpoint health calculator | M |
| **P3** | 5.1 | Skip scan awareness | L |
| **P3** | 7.1-7.2 | Schema inspection updates | S |
| **P3** | 4.6 | I/O health monitoring | L |

**S** = small (<1h), **M** = medium (1-3h), **L** = large (3h+)

---

## Files Changed (Full List)

| File | Changes |
|------|---------|
| `tests/conftest.py` | Add PG 17, 18 to params |
| `tests/Dockerfile.postgres-hypopg` | Verify PG 17/18 builds |
| `pyproject.toml` | Bump pglast if needed for PG 18 |
| `src/postgres_mcp/sql/pg_compat.py` | **NEW** — shared version helpers |
| `src/postgres_mcp/sql/safe_sql.py` | Add PG 17/18 functions to whitelist |
| `src/postgres_mcp/sql/extension_utils.py` | No changes (works as-is) |
| `src/postgres_mcp/top_queries/top_queries_calc.py` | PG 17/18 column branches |
| `src/postgres_mcp/index/index_opt_base.py` | Fix PG 12 bug + use shared helper |
| `src/postgres_mcp/explain/explain_plan.py` | MEMORY, SERIALIZE options |
| `src/postgres_mcp/tools/query_tools.py` | Expose new EXPLAIN params |
| `src/postgres_mcp/database_health/replication_calc.py` | New slot columns PG 17+ |
| `src/postgres_mcp/database_health/vacuum_health_calc.py` | Timing columns PG 18+ |
| `src/postgres_mcp/database_health/connection_health_calc.py` | Wait events PG 17+ |
| `src/postgres_mcp/database_health/constraint_health_calc.py` | conforced PG 18+ |
| `src/postgres_mcp/database_health/checkpoint_health_calc.py` | **NEW** — PG 17+ |
| `src/postgres_mcp/tools/schema_tools.py` | Virtual generated cols PG 18+ |
| `src/postgres_mcp/artifacts.py` | New fields for EXPLAIN/replication |

---

## Breaking Changes Cheatsheet

### PG 16 → PG 17
- `pg_stat_statements`: `blk_read_time` → `shared_blk_read_time`, `blk_write_time` → `shared_blk_write_time`
- `pg_stat_bgwriter`: `buffers_backend`, `buffers_backend_fsync` removed
- `pg_stat_progress_vacuum`: column renames (`max_dead_tuples` → `max_dead_tuple_bytes`, `num_dead_tuples` → `num_dead_item_ids`)
- `pg_collation`: `colliculocale` → `colllocale`
- `pg_database`: `daticulocale` → `datlocale`

### PG 17 → PG 18
- `pg_stat_wal`: `wal_write`, `wal_sync`, `wal_write_time`, `wal_sync_time` **removed** (moved to `pg_stat_io`)
- `pg_stat_io`: `op_bytes` removed (replaced by `read_bytes`/`write_bytes`/`extend_bytes`)
- `pg_backend_memory_contexts`: `parent` removed (replaced by `path`); `level` now 1-based
- `pg_attribute`: `attcacheoff` removed
- `EXPLAIN ANALYZE` now includes BUFFERS automatically
- VACUUM/ANALYZE auto-includes inheritance children by default
- Generated columns default to VIRTUAL (was STORED)
- Docker data dir: `/var/lib/postgresql/18/data`
- MD5 passwords emit deprecation warnings

### Not affected (all safe PG 12–18)
- `information_schema` views (schemata, tables, columns, sequences, table_constraints, key_column_usage)
- `pg_class`, `pg_namespace`, `pg_index`, `pg_am`, `pg_extension`, `pg_indexes`
- `pg_stat_activity` (state, count queries)
- `pg_stat_user_tables` (relname, last_vacuum, last_autovacuum)
- `pg_stat_user_indexes` (idx_scan, indexrelid)
- `pg_statio_user_indexes`, `pg_statio_user_tables`
- `pg_stats` (tablename, attname, avg_width, n_distinct, null_frac)
- `pg_stat_replication` (state)
- `pg_replication_slots` (slot_name, database, active — existing columns)
- Functions: `pg_is_in_recovery()`, `pg_last_wal_*()`, `pg_get_indexdef()`, `pg_relation_size()`, `pg_total_relation_size()`, `pg_get_expr()`, `has_sequence_privilege()`, `format_type()`, `hypopg_*()`, `SHOW server_version`
