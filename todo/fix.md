# postgres-mcp Server Audit Fixes

**Status: DONE** - All fixes implemented and verified. CI passes (ruff format, ruff check, pyright, 191 tests).

## What Changed

### Module Structure (refactor from 694-line `server.py`)

```
src/postgres_mcp/
  server.py                      (260 lines) - mcp instance, tool registration, main(), shutdown(), re-exports
  tools/
    __init__.py                  (0 lines)
    _types.py                    (8 lines) - ResponseType alias, PG_STAT_STATEMENTS constant
    _response.py                 (28 lines) - format_text_response, format_error_response
    _state.py                    (33 lines) - AccessMode, db_connection, get_sql_driver
    schema_tools.py              (248 lines) - list_schemas, list_objects, get_object_details
    query_tools.py               (93 lines) - execute_sql, explain_query
    analysis_tools.py            (104 lines) - analyze_workload/query_indexes, analyze_db_health, get_top_queries
```

### Fixes Applied

| # | Fix | Details |
|---|-----|---------|
| 1 | JSON formatting | `format_text_response()` uses `json.dumps(data, indent=2, default=str)` for non-string data instead of `str()` |
| 2 | `isError` flag | `format_error_response()` returns `CallToolResult(isError=True)` |
| 3 | Bad default removed | `execute_sql.sql` param no longer has `default="all"` |
| 4 | Dead re-raises removed | 3 redundant `except Exception: raise` blocks removed from `explain_query` |
| 5 | DRY helper | `_create_index_tool(sql_driver, method)` extracted in `analysis_tools.py` |
| 6 | Service prefix | All 9 tools registered as `postgres_*` (e.g. `postgres_list_schemas`) |
| 7 | Complete annotations | All tools have `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` |

### Additional Improvements

- **Pagination** added to `postgres_list_objects` (SQL LIMIT/OFFSET) and `postgres_execute_sql` (Python slicing)
- **`@validate_call` removed** from `analyze_workload_indexes` and `analyze_query_indexes` (FastMCP validates already)
- **`execute_sql` annotations** vary by access mode: `destructiveHint=True` in unrestricted, read-only hints in restricted

### Architecture Decisions

- **`mcp.add_tool()` registration** (not decorators) to avoid circular imports
- **State in `_state.py`** - `server.py` sets state via `import postgres_mcp.tools._state as state`
- **Backward-compatible re-exports** in `server.py` (`list_schemas`, `explain_query`, `AccessMode`, etc.) typed as `Any` to match old `@mcp.tool()` decorator behavior
- **All tool functions return `CallToolResult`** - FastMCP rejects `Union` or `Optional` with `CallToolResult` in return type annotations

### Test Updates (4 files)

| File | Changes |
|------|---------|
| `tests/unit/explain/test_server_integration.py` | Patch targets to `postgres_mcp.tools.query_tools.*`, explicit params to avoid Field() issues, `CallToolResult` assertions |
| `tests/unit/test_access_mode.py` | Patch targets to `postgres_mcp.tools._state.*`, direct state access via `_state` module |
| `tests/unit/sql/test_readonly_enforcement.py` | Patch targets to `postgres_mcp.tools._state.*` |
| `tests/unit/test_transport.py` | Patch `_state.db_connection.pool_connect` |

`tests/unit/explain/test_server.py` - no changes needed (uses `patch.object(server, ...)` which works via re-export).

## Not Changed (deferred)

- `safe_sql.py` (1036 lines) - mostly constant lists, out of scope
- SSE deprecation warning - minor
- DNS rebinding protection - requires upstream FastMCP changes
- Lifespan/Context injection - bigger architectural change, separate PR
