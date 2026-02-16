# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

postgres-mcp is a Python MCP (Model Context Protocol) server that provides PostgreSQL database analysis and management tools to LLM clients. It exposes tools for health checks, index tuning, query explain plans, schema inspection, SQL execution, and workload analysis via the FastMCP framework.

This is a [vcode](https://x.com/vcode_sh) fork of the original [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp).

## Commands

```bash
# Install dependencies
uv sync

# Run all tests (requires Docker for integration tests)
uv run pytest -v --log-cli-level=INFO

# Run a single test file
uv run pytest tests/unit/test_obfuscate_password.py

# Run a specific test
uv run pytest tests/unit/test_db_conn_pool.py::test_pool_connect_success

# Lint and format
uv run ruff format --check .
uv run ruff check .

# Auto-fix formatting
uv run ruff format .

# Type checking
uv run pyright

# Build package
uv build
```

CI runs: `ruff format --check .` → `ruff check .` → `pyright` → `pytest -v --log-cli-level=INFO`

## Architecture

**Entry point**: `src/postgres_mcp/__init__.py` → `server.py::main()` bootstraps the FastMCP server, parses CLI args (database URL, access mode, transport), sets up a connection pool, and registers 9 MCP tools.

**Access modes**: `UNRESTRICTED` (full read/write) vs `RESTRICTED` (read-only with safety enforcement via SafeSqlDriver).

**Transports**: stdio (default), sse, streamable-http.

### Core Modules (`src/postgres_mcp/`)

- **`server.py`** (~260 lines) — FastMCP instance, tool registration via `mcp.add_tool()`, `main()`, `shutdown()`, and backward-compatible re-exports.
- **`tools/`** — Tool implementations split by domain:
  - `_state.py` — Shared state: `AccessMode` enum, `db_connection`, `current_access_mode`, `get_sql_driver()`
  - `_response.py` — `format_text_response()` (JSON serialization) and `format_error_response()` (with MCP `isError` flag)
  - `_types.py` — `ResponseType` alias, constants
  - `schema_tools.py` (~248 lines) — `postgres_list_schemas`, `postgres_list_objects`, `postgres_get_object_details`
  - `query_tools.py` (~93 lines) — `postgres_execute_sql`, `postgres_explain_query`
  - `analysis_tools.py` (~104 lines) — `postgres_analyze_workload_indexes`, `postgres_analyze_query_indexes`, `postgres_analyze_db_health`, `postgres_get_top_queries`
- **`sql/`** — Database access layer. `SqlDriver` is the base async driver; `SafeSqlDriver` wraps it for restricted mode with query parsing, function whitelisting, and timeouts. `DbConnPool` manages the async connection pool. `bind_params.py` handles SQL parsing via `pglast`.
- **`database_health/`** — Composed health calculators (index, buffer, connection, replication, sequence, constraint, vacuum) orchestrated by `DatabaseHealthTool`
- **`index/`** — Database Tuning Advisor (`dta_calc.py`) uses hypothetical indexes via HypoPG to recommend indexes. `llm_opt.py` adds LLM-based refinement. `index_opt_base.py` contains the shared optimization logic.
- **`explain/`** — EXPLAIN/EXPLAIN ANALYZE plan generation with bind variable replacement and PG 16+ generic plan support
- **`top_queries/`** — Query performance stats from `pg_stat_statements`
- **`artifacts.py`** — Pydantic/attrs data models for tool responses

### Tool Registration Pattern

Tool modules export plain async functions. `server.py` imports them and registers via `mcp.add_tool()` with name, description, and `ToolAnnotations`. This avoids circular imports. All 9 tools are prefixed with `postgres_` (e.g. `postgres_list_schemas`). State is shared via `tools/_state.py` which `main()` mutates at startup.

### Key Patterns

- All database operations are async (asyncio + psycopg async)
- PostgreSQL version is detected at runtime for feature compatibility (e.g., generic plans require PG 16+)
- Integration tests spin up Docker containers with parameterized PG versions (12, 15, 16) via `tests/conftest.py`
- SQL parsing uses `pglast` for AST-level analysis (parameter binding, table/column discovery, safety checks)
- All tool functions return `CallToolResult` (FastMCP rejects `Union`/`Optional` with `CallToolResult` in return types)
- Response formatting: `format_text_response` uses `json.dumps` for structured data; `format_error_response` sets `isError=True`

## Code Style

- Ruff: line length 150, double quotes, Python 3.9+ target
- Import style: one import per line (`from x import y`), sorted
- Type checking: pyright in standard mode
- Docstrings: Google convention

## Rules

- Always write code and documentation in English.
- Always write code in a way that is easy to understand and maintain.
- Always keep the code clean and readable. Use consistent naming conventions.
- Always plan and write code in modular architecture.
- Keep files loc less than 280 lines.
