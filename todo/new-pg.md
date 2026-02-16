# PostgreSQL 17 & 18 Expansion Plan (Audit + Research)

**Status:** Updated after full repository audit and external research on **February 16, 2026**.

## 1. Audit Snapshot (Current Codebase)

### 1.1 Verified project state
- MCP server uses `FastMCP` with 9 tools, registered in `src/postgres_mcp/server.py`.
- Tool surface is split cleanly by domain:
  - `src/postgres_mcp/tools/schema_tools.py`
  - `src/postgres_mcp/tools/query_tools.py`
  - `src/postgres_mcp/tools/analysis_tools.py`
- SQL safety is centralized in `src/postgres_mcp/sql/safe_sql.py` (restricted mode).
- PostgreSQL version logic is currently duplicated:
  - major version via `SHOW server_version` in `src/postgres_mcp/sql/extension_utils.py`
  - numeric version via `SHOW server_version_num` in `src/postgres_mcp/database_health/replication_calc.py`
- Current test fixture matrix is `postgres:12`, `postgres:15`, `postgres:16` in `tests/conftest.py`.

### 1.2 Local quality checks executed during audit
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit -q` -> `167 passed, 24 skipped, 1 xfailed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` -> passed
- `UV_CACHE_DIR=/tmp/uv-cache uv run pyright` -> `0 errors`

### 1.3 Critical gaps found
- **P0:** `src/postgres_mcp/index/index_opt_base.py` uses `total_exec_time` unconditionally in `_get_query_stats_direct()` (breaks PG12 where column is `total_time`).
- **P0:** Restricted mode blocks PostgreSQL 17 SQL/JSON constructs because AST node types are missing from `ALLOWED_NODE_TYPES` (for example `JsonFuncExpr`, `JsonTable`), even when statement is read-only.
- **P0:** `pglast==7.11` is built on PG parser `17.7`; parser probes show PG18 grammar gaps (for example `VIRTUAL` generated columns, `NOT ENFORCED`, `WITHOUT OVERLAPS` fail to parse).
- **P1:** Plan typo: catalog column is `pg_constraint.conenforced` (not `conforced`).
- **P1:** Version/capability checks are not centralized; this will become fragile as PG17/18 branching grows.

## 2. Research Findings Relevant to This Repo

### 2.1 PostgreSQL 17/18 changes that directly affect this code
- **EXPLAIN enhancements**
  - PG17 adds `EXPLAIN (MEMORY)` and `EXPLAIN (ANALYZE, SERIALIZE ...)`.
  - PG18 includes buffer usage automatically with `EXPLAIN ANALYZE`.
- **`pg_stat_statements` evolution**
  - PG17 adds `stats_since`, `minmax_stats_since`, `local_blk_read_time`, `local_blk_write_time`.
  - PG18 adds `parallel_workers_to_launch`, `parallel_workers_launched`, `wal_buffers_full`.
- **Replication monitoring**
  - PG17 adds `invalidation_reason`, `inactive_since`, `failover`, `synced` to `pg_replication_slots`.
- **Wait events**
  - PG17 adds `pg_wait_events`, enabling enriched connection diagnostics.
- **Checkpoint stats**
  - PG17 introduces `pg_stat_checkpointer` (split from old bgwriter responsibility).
  - PG18 extends it (`num_done`, `slru_written`).
- **Vacuum timing**
  - PG18 adds `total_vacuum_time`, `total_autovacuum_time`, `total_analyze_time`, `total_autoanalyze_time` to `pg_stat_all_tables`.
- **Schema/constraints**
  - PG18 defaults generated columns to `VIRTUAL`.
  - PG18 introduces `ENFORCED` / `NOT ENFORCED` constraints and catalog field `pg_constraint.conenforced`.
- **Planner behavior**
  - PG18 introduces B-tree skip scan (can reduce need for some recommended indexes).

### 2.2 MCP implementation guidance that impacts rollout
- Keep tool names stable (`postgres_*`) and add only backward-compatible optional parameters.
- Keep annotations accurate (`readOnlyHint`, `destructiveHint`, `idempotentHint`) especially when behavior differs by access mode.
- Keep transport support aligned with docs (stdio + streamable HTTP/SSE) while avoiding breaking client configs.
- Treat tool output contracts as public API: changes should be additive, with tests for legacy response shape.

## 3. Architecture Direction for Modular, Coherent Expansion

### 3.1 Add a dedicated compatibility layer
Create `src/postgres_mcp/sql/pg_compat.py` and move all version/capability decisions there.

**Responsibilities:**
- unified server version retrieval (prefer `server_version_num`, derive major from it)
- connection-scoped caching (not single global process cache)
- capability probing helpers:
  - view has column (`pg_attribute` / `information_schema.columns`)
  - extension view has column (`pg_stat_statements`, `pg_replication_slots`)
  - feature flags (EXPLAIN options available, wait events view available)

This prevents version branching from spreading across tools.

### 3.2 Rule for compatibility logic
- Prefer **capability checks** over pure major-version checks where possible.
- Keep version checks only as a fast path; fallback to capability probing for safety on managed/custom builds.

## 4. Implementation Plan

## Phase 0: Foundation (P0)

### 0.1 Implement `pg_compat.py`
**New file:** `src/postgres_mcp/sql/pg_compat.py`

Add:
- `PgServerInfo` dataclass (`server_version_num`, `major`, cache key)
- `get_server_info(sql_driver)`
- `has_view_column(sql_driver, schema, view, column)`
- `has_pg_stat_statements_column(sql_driver, column)`

### 0.2 Refactor existing version logic to use `pg_compat`
- `src/postgres_mcp/sql/extension_utils.py`
- `src/postgres_mcp/database_health/replication_calc.py`
- `src/postgres_mcp/explain/explain_plan.py`
- `src/postgres_mcp/top_queries/top_queries_calc.py`
- `src/postgres_mcp/index/index_opt_base.py`

## Phase 1: Compatibility Fixes (P0)

### 1.1 Expand test matrix to PG17/18
- Update `tests/conftest.py` to include `postgres:17`, `postgres:18`.
- Keep the fixture version list explicit and deterministic.

### 1.2 Validate HypoPG build/runtime on PG17/18
- Keep `tests/Dockerfile.postgres-hypopg` but add explicit CI smoke coverage:
  - image build succeeds
  - `CREATE EXTENSION hypopg` succeeds
  - `EXPLAIN` with `hypopg_create_index()` works

### 1.3 Fix PG12 bug in index workload query stats
- Update `src/postgres_mcp/index/index_opt_base.py` to use compatibility-selected timing columns.
- Reuse shared `pg_stat_statements` column resolver from `pg_compat.py`.

## Phase 2: Top Queries Enhancements (P1)

### 2.1 Extend selected columns in `TopQueriesCalc`
**File:** `src/postgres_mcp/top_queries/top_queries_calc.py`

Add optional output fields when available:
- PG17: `stats_since`, `minmax_stats_since`, `local_blk_read_time`, `local_blk_write_time`
- PG18: `parallel_workers_to_launch`, `parallel_workers_launched`, `wal_buffers_full`

### 2.2 Keep output contract backward-compatible
- Existing keys stay unchanged.
- New keys are additive and may be `null` when unavailable.

### 2.3 Update tests
- `tests/unit/top_queries/test_top_queries_calc.py`
- add PG17/PG18 mocks for new columns
- include fallback tests where capability probes return false

## Phase 3: EXPLAIN Enhancements (P1)

### 3.1 Add PG17 options to API
**Files:**
- `src/postgres_mcp/explain/explain_plan.py`
- `src/postgres_mcp/tools/query_tools.py`

Add optional params:
- `include_memory: bool = False`
- `serialize: Literal["text", "binary"] | None = None` (valid only with `analyze=True`)

### 3.2 Validate and gate options
- If unsupported by server, return clear error (not generic exception).
- Keep existing default behavior untouched.

### 3.3 Ensure artifacts remain tolerant
- `src/postgres_mcp/artifacts.py` already ignores unknown plan keys effectively via selective extraction.
- Add tests for plans containing new PG18 node keys.

## Phase 4: Health Checks Expansion (P1/P2)

### 4.1 Replication slots enrichment (PG17+)
**File:** `src/postgres_mcp/database_health/replication_calc.py`

Enhance `ReplicationSlot` dataclass with optional fields:
- `invalidation_reason`
- `inactive_since`
- `failover`
- `synced`

### 4.2 Connection diagnostics with wait events (PG17+)
**File:** `src/postgres_mcp/database_health/connection_health_calc.py`

When `pg_wait_events` is available, include grouped wait-event context for `idle in transaction`.

### 4.3 Vacuum timing metrics (PG18+)
**File:** `src/postgres_mcp/database_health/vacuum_health_calc.py`

If timing columns exist, include aggregate/manual/autovacuum time in output.

### 4.4 New checkpoint calculator
**New file:** `src/postgres_mcp/database_health/checkpoint_health_calc.py`

Read from `pg_stat_checkpointer`, include PG18 extras when present.
Register in `src/postgres_mcp/database_health/database_health.py` and expose via `HealthType`.

### 4.5 Constraint enforcement awareness (PG18+)
**File:** `src/postgres_mcp/database_health/constraint_health_calc.py`

Correct field name and logic:
- use `conenforced` (PG18+)
- distinguish:
  - invalid (`convalidated = false`)
  - not enforced (`conenforced = false`)

## Phase 5: SafeSqlDriver + Parser Strategy (P0/P1)

### 5.1 Fix AST node allowlist for PG17 SQL/JSON
**File:** `src/postgres_mcp/sql/safe_sql.py`

Add missing AST node types to `ALLOWED_NODE_TYPES` (at minimum):
- `JsonFuncExpr`
- `JsonTable`

This is required; function-name whitelisting alone is not enough.

### 5.2 Expand function whitelist conservatively
Add only verified, read-safe functions needed by real queries in this server context.
Candidate PG18 additions:
- `uuidv4`, `uuidv7`, `uuid_extract_timestamp`, `uuid_extract_version`
- `array_sort`, `array_reverse`
- `casefold`, `crc32`, `crc32c`

Do not add write-oriented or irrelevant functions without explicit usage need.

### 5.3 Handle PG18 parser gap explicitly
`pglast==7.11` currently parses with PostgreSQL parser `17.7`.

Observed local probe results:
- parse **OK**: `EXPLAIN MEMORY`, `EXPLAIN ... SERIALIZE`, `RETURNING old/new`
- parse **FAIL**: `VIRTUAL` generated columns, `NOT ENFORCED`, `WITHOUT OVERLAPS`

Plan:
- Check if a newer `pglast` release supports PG18 grammar.
- If unavailable, keep clear restricted-mode error messages for unsupported grammar and document limitation.

### 5.4 Add parser regression tests
**File:** `tests/unit/sql/test_safe_sql.py`

Add explicit tests for:
- allowed PG17 SQL/JSON read-only queries
- PG18 syntax that is currently parser-limited (assert deterministic, clear error)

## Phase 6: Schema Tool Improvements (P2)

### 6.1 Surface generated-column metadata
**File:** `src/postgres_mcp/tools/schema_tools.py`

Extend `information_schema.columns` selection with:
- `is_generated`
- `generation_expression`

Keep existing fields unchanged.

### 6.2 Surface enforcement metadata where relevant
When returning constraint details, include enforcement/validation flags when available.

## Phase 7: Planner-Aware Index Recommendations (P3)

### 7.1 PG18 skip-scan awareness
**Files:**
- `src/postgres_mcp/index/index_opt_base.py`
- `src/postgres_mcp/index/dta_calc.py`

If recommendation is likely redundant because existing multicolumn index can be used via skip scan, annotate recommendation with lower confidence/priority instead of dropping silently.

## 9. CI and Validation Strategy

### 5.1 Add compatibility-focused CI job
**File:** `.github/workflows/build.yml`

Keep current pipeline, add a focused matrix job for compatibility smoke tests:
- PG12/16/17/18
- top queries compatibility check
- explain compatibility check
- safe_sql parser compatibility check

This avoids running the entire heavy integration suite for every matrix cell.

### 5.2 Keep full integration runs for scheduled/nightly or release pipelines
Use full DTA + health integration on a reduced cadence to control PR latency.

## 10. Prioritized Execution Order

| Priority | Work Item | Why |
|---|---|---|
| P0 | Phase 0 (`pg_compat` foundation) | Unblocks all later version branching |
| P0 | Phase 1.3 (`total_exec_time` bug fix) | Existing PG12 correctness issue |
| P0 | Phase 5.1 (SafeSql AST node fixes) | Current PG17 read-only SQL/JSON breakage |
| P0 | Phase 5.3 (parser strategy for PG18) | Required for realistic PG18 support claims |
| P1 | Phase 2 (top queries new columns) | High-value observability improvements |
| P1 | Phase 3 (EXPLAIN options) | Exposes new PG17/18 planner telemetry |
| P1 | Phase 4.1/4.2/4.5 | Replication and constraint health correctness |
| P2 | Phase 4.3/4.4, Phase 6 | Health + schema depth improvements |
| P3 | Phase 7 | Planner intelligence tuning |

## 11. Files Expected to Change

- `src/postgres_mcp/sql/pg_compat.py` (**new**)
- `src/postgres_mcp/sql/extension_utils.py`
- `src/postgres_mcp/sql/safe_sql.py`
- `src/postgres_mcp/top_queries/top_queries_calc.py`
- `src/postgres_mcp/index/index_opt_base.py`
- `src/postgres_mcp/explain/explain_plan.py`
- `src/postgres_mcp/tools/query_tools.py`
- `src/postgres_mcp/tools/schema_tools.py`
- `src/postgres_mcp/database_health/replication_calc.py`
- `src/postgres_mcp/database_health/connection_health_calc.py`
- `src/postgres_mcp/database_health/vacuum_health_calc.py`
- `src/postgres_mcp/database_health/constraint_health_calc.py`
- `src/postgres_mcp/database_health/checkpoint_health_calc.py` (**new**)
- `src/postgres_mcp/database_health/database_health.py`
- `tests/conftest.py`
- `tests/unit/top_queries/test_top_queries_calc.py`
- `tests/unit/sql/test_safe_sql.py`
- `.github/workflows/build.yml`
- `README.md` (version support matrix and behavior notes)

## 12. Source Links Used for Research

### PostgreSQL official docs/release notes
- [PostgreSQL 17 Release Notes](https://www.postgresql.org/docs/17/release-17.html)
- [PostgreSQL 18 Release Notes](https://www.postgresql.org/docs/18/release-18.html)
- [EXPLAIN (PG 17)](https://www.postgresql.org/docs/17/sql-explain.html)
- [EXPLAIN (PG 18)](https://www.postgresql.org/docs/18/sql-explain.html)
- [pg_stat_statements (PG 17)](https://www.postgresql.org/docs/17/pgstatstatements.html)
- [pg_stat_statements (PG 18)](https://www.postgresql.org/docs/18/pgstatstatements.html)
- [pg_replication_slots view (PG 17)](https://www.postgresql.org/docs/17/view-pg-replication-slots.html)
- [pg_replication_slots view (PG 18)](https://www.postgresql.org/docs/18/view-pg-replication-slots.html)
- [Monitoring Statistics (PG 17)](https://www.postgresql.org/docs/17/monitoring-stats.html)
- [Monitoring Statistics (PG 18)](https://www.postgresql.org/docs/18/monitoring-stats.html)
- [pg_constraint catalog (PG 18)](https://www.postgresql.org/docs/18/catalog-pg-constraint.html)
- [CREATE TABLE (PG 18)](https://www.postgresql.org/docs/18/sql-createtable.html)

### MCP docs
- [MCP: Tools concept](https://modelcontextprotocol.io/docs/concepts/tools)
- [MCP: Tool annotations](https://modelcontextprotocol.io/docs/concepts/tools#tool-annotations)
- [MCP: Security best practices](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices)

### Related upstream projects
- [HypoPG repository](https://github.com/HypoPG/hypopg)
- [pglast repository](https://github.com/lelit/pglast)
