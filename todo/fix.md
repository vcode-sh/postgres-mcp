# Plan: postgres-mcp Server Audit Fixes

## Context

`server.py` is 694 lines (limit: 280). All tool responses use Python `str()` instead of JSON. Error responses lack the MCP `isError` flag. Tool names have no service prefix (collision risk). Annotations are incomplete. Several code quality issues exist (dead code, duplication, bad defaults). This plan addresses all findings from the audit.

## Module Structure After Refactor

```
src/postgres_mcp/
  __init__.py                    (unchanged)
  server.py                      (~250 lines) - mcp instance, tool registration, main(), shutdown()
  tools/
    __init__.py                  (~5 lines)
    _types.py                    (~15 lines) - ResponseType, constants
    _response.py                 (~35 lines) - format_text_response, format_error_response
    _state.py                    (~40 lines) - AccessMode, db_connection, get_sql_driver
    schema_tools.py              (~250 lines) - list_schemas, list_objects, get_object_details
    query_tools.py               (~100 lines) - execute_sql, explain_query
    analysis_tools.py            (~115 lines) - analyze_workload/query_indexes, analyze_db_health, get_top_queries
```

## Key Architectural Decisions

### Tool registration via `mcp.add_tool()` (not decorators)

Tool modules export plain async functions. `server.py` imports them and registers via `mcp.add_tool()` with name, description, and annotations. This avoids circular imports (`server.py` -> tools -> server.py for `mcp` instance). This is the same pattern already used for `execute_sql`.

### State in `_state.py`

`db_connection`, `current_access_mode`, `shutdown_in_progress`, `get_sql_driver()` live in `tools/_state.py`. Tool modules import from there. `main()` in server.py sets state via `import postgres_mcp.tools._state as state; state.current_access_mode = ...`.

### Test backward compatibility via re-exports + targeted patch updates

- `server.py` re-exports `AccessMode`, `get_sql_driver`, `format_text_response`, `format_error_response`, `explain_query` etc. so `from postgres_mcp.server import X` still works
- **4 test files** need patch target updates (because `patch()` must target the module where the name is **used**, not where it's re-exported)

---

## Changes by File

### NEW: `src/postgres_mcp/tools/__init__.py`
Empty package init.

### NEW: `src/postgres_mcp/tools/_types.py`
- `ResponseType` alias (moved from server.py)
- `PG_STAT_STATEMENTS` and `HYPOPG_EXTENSION` constants

### NEW: `src/postgres_mcp/tools/_response.py`

**Fix 1 - JSON formatting:** `format_text_response()` uses `json.dumps(data, indent=2, default=str)` for non-string data instead of `str()`.

**Fix 2 - isError flag:** `format_error_response()` returns `CallToolResult(content=[TextContent(...)], isError=True)` instead of plain text with "Error:" prefix.

### NEW: `src/postgres_mcp/tools/_state.py`
- `AccessMode` enum (moved from server.py)
- `db_connection = DbConnPool()` (moved from server.py)
- `current_access_mode` (moved from server.py)
- `shutdown_in_progress` (moved from server.py)
- `get_sql_driver()` (moved from server.py)

### NEW: `src/postgres_mcp/tools/schema_tools.py`
- `postgres_list_schemas()` - moved from server.py, renamed
- `postgres_list_objects()` - moved, renamed, **+pagination** (`offset`/`limit` params, applied via SQL LIMIT/OFFSET)
- `postgres_get_object_details()` - moved, renamed
- Return type: `ResponseType | CallToolResult`

### NEW: `src/postgres_mcp/tools/query_tools.py`
- `postgres_execute_sql()` - moved, renamed
  - **Fix 3:** Remove `default="all"` from `sql` parameter
  - **+pagination:** `offset`/`limit` params (applied in Python after fetch, since user SQL is arbitrary)
- `postgres_explain_query()` - moved, renamed
  - **Fix 4:** Remove 3 redundant `except Exception: raise` blocks

### NEW: `src/postgres_mcp/tools/analysis_tools.py`
- `_create_index_tool(sql_driver, method)` - **Fix 5: DRY** helper extracted from duplicated code
- `postgres_analyze_workload_indexes()` - moved, renamed, uses helper, `@validate_call` removed (FastMCP validates already)
- `postgres_analyze_query_indexes()` - moved, renamed, uses helper, `@validate_call` removed
- `postgres_analyze_db_health()` - moved, renamed
- `postgres_get_top_queries()` - moved, renamed

### REWRITTEN: `src/postgres_mcp/server.py`

Structure:
1. Imports from tools subpackage
2. `mcp = FastMCP("postgres-mcp")`
3. `_register_tools()` - registers 8 read-only tools via `mcp.add_tool()` at module level
4. Re-exports for backward compatibility
5. `main()` - CLI parsing, sets `state.current_access_mode`, registers `execute_sql` conditionally, DB connection, transport
6. `shutdown()` - reads/writes `state.shutdown_in_progress`, closes `state.db_connection`

**Fix 6 - Service prefix:** All tools registered with `name="postgres_..."`:
| Old Name | New Name |
|----------|----------|
| `list_schemas` | `postgres_list_schemas` |
| `list_objects` | `postgres_list_objects` |
| `get_object_details` | `postgres_get_object_details` |
| `explain_query` | `postgres_explain_query` |
| `execute_sql` | `postgres_execute_sql` |
| `analyze_workload_indexes` | `postgres_analyze_workload_indexes` |
| `analyze_query_indexes` | `postgres_analyze_query_indexes` |
| `analyze_db_health` | `postgres_analyze_db_health` |
| `get_top_queries` | `postgres_get_top_queries` |

**Fix 7 - Complete annotations:** Every tool gets all 4 hints:
| Tool | readOnly | destructive | idempotent | openWorld |
|------|----------|-------------|------------|-----------|
| list_schemas | True | False | True | False |
| list_objects | True | False | True | False |
| get_object_details | True | False | True | False |
| explain_query | True | False | True | False |
| execute_sql (unrestricted) | - | True | False | False |
| execute_sql (restricted) | True | False | True | False |
| analyze_workload_indexes | True | False | True | False |
| analyze_query_indexes | True | False | True | False |
| analyze_db_health | True | False | True | False |
| get_top_queries | True | False | True | False |

### UPDATED: Test files (4 files)

**`tests/unit/explain/test_server_integration.py`:**
- `from postgres_mcp.server import explain_query` -> still works (re-exported)
- Patch targets change:
  - `postgres_mcp.server.format_text_response` -> `postgres_mcp.tools.query_tools.format_text_response`
  - `postgres_mcp.server.format_error_response` -> `postgres_mcp.tools.query_tools.format_error_response`
  - `postgres_mcp.server.get_sql_driver` -> `postgres_mcp.tools.query_tools.get_sql_driver`
  - `postgres_mcp.server.ExplainPlanTool` -> `postgres_mcp.tools.query_tools.ExplainPlanTool`
- **Fix format_error_response mock:** Since it now returns `CallToolResult`, update the test that checks error handling (test_explain_query_error_handling_integration) to expect `CallToolResult` with `isError=True` instead of a list with "Error:" prefix text

**`tests/unit/test_access_mode.py`:**
- `from postgres_mcp.server import AccessMode, get_sql_driver` -> still works (re-exported)
- Patch targets change:
  - `postgres_mcp.server.current_access_mode` -> `postgres_mcp.tools._state.current_access_mode`
  - `postgres_mcp.server.db_connection` -> `postgres_mcp.tools._state.db_connection`
- `postgres_mcp.server.mcp.*`, `postgres_mcp.server.shutdown` -> unchanged (stay in server.py)
- Direct assignment `postgres_mcp.server.current_access_mode = ...` -> `postgres_mcp.tools._state.current_access_mode = ...`
- Assertion `postgres_mcp.server.current_access_mode == ...` -> `postgres_mcp.tools._state.current_access_mode == ...`

**`tests/unit/sql/test_readonly_enforcement.py`:**
- Imports unchanged (re-exported)
- Patch targets change:
  - `postgres_mcp.server.current_access_mode` -> `postgres_mcp.tools._state.current_access_mode`
  - `postgres_mcp.server.db_connection` -> `postgres_mcp.tools._state.db_connection`

**`tests/unit/test_transport.py`:**
- `from postgres_mcp.server import main, mcp` -> unchanged (stay in server.py)
- `postgres_mcp.server.db_connection.pool_connect` -> `postgres_mcp.tools._state.db_connection.pool_connect` (method patch on shared object would technically work either way, but update for consistency)
- `postgres_mcp.server.mcp.*` -> unchanged

**`tests/unit/explain/test_server.py`:**
- `import postgres_mcp.server as server` + `server.explain_query` -> works via re-export
- `patch.object(server, "explain_query", ...)` -> works (patches the re-exported name)
- **No changes needed**

---

## Implementation Order

1. Create `tools/` package: `__init__.py`, `_types.py`, `_response.py`, `_state.py`
2. Create `tools/schema_tools.py` (move + rename tools)
3. Create `tools/query_tools.py` (move + rename + fix default + remove re-raise)
4. Create `tools/analysis_tools.py` (move + rename + DRY helper + remove @validate_call)
5. Rewrite `server.py` (registration + main + shutdown + re-exports)
6. Update 4 test files (patch targets + error format expectations)
7. Run verification: `uv run ruff format . && uv run ruff check . && uv run pyright && uv run pytest -v --log-cli-level=INFO`

## Verification

```bash
# Formatting + linting
uv run ruff format --check .
uv run ruff check .

# Type checking
uv run pyright

# All tests (unit + integration with Docker)
uv run pytest -v --log-cli-level=INFO

# Quick unit-only sanity check
uv run pytest tests/unit/ -v
```

## What This Plan Does NOT Change

- `safe_sql.py` (1036 lines) - mostly constant lists, out of scope
- `dta_calc.py`, `bind_params.py`, `index_opt_base.py` etc. - not MCP-server related
- SSE deprecation warning - minor, deferred
- DNS rebinding protection - deferred (requires upstream FastMCP changes)
- Lifespan/Context injection - deferred (bigger architectural change, separate PR)
- Pydantic BaseModel input classes - current Field() pattern works fine with FastMCP
