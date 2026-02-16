# ruff: noqa: B008
import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import postgres_mcp.tools._state as state

from .sql import obfuscate_password
from .tools._response import format_error_response
from .tools._response import format_text_response
from .tools._state import AccessMode
from .tools._state import get_sql_driver
from .tools._types import PG_STAT_STATEMENTS
from .tools._types import ResponseType
from .tools.analysis_tools import postgres_analyze_db_health
from .tools.analysis_tools import postgres_analyze_query_indexes
from .tools.analysis_tools import postgres_analyze_workload_indexes
from .tools.analysis_tools import postgres_get_top_queries
from .tools.query_tools import postgres_execute_sql
from .tools.query_tools import postgres_explain_query
from .tools.schema_tools import postgres_get_object_details
from .tools.schema_tools import postgres_list_objects
from .tools.schema_tools import postgres_list_schemas

mcp = FastMCP("postgres-mcp")

logger = logging.getLogger(__name__)

# Annotations shared by all read-only tools
_READONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _register_readonly_tools() -> None:
    """Register all read-only tools at module load time."""
    mcp.add_tool(
        postgres_list_schemas,
        name="postgres_list_schemas",
        description="List all schemas in the database",
        annotations=ToolAnnotations(title="List Schemas", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )
    mcp.add_tool(
        postgres_list_objects,
        name="postgres_list_objects",
        description="List objects in a schema",
        annotations=ToolAnnotations(title="List Objects", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )
    mcp.add_tool(
        postgres_get_object_details,
        name="postgres_get_object_details",
        description="Show detailed information about a database object",
        annotations=ToolAnnotations(title="Get Object Details", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )
    mcp.add_tool(
        postgres_explain_query,
        name="postgres_explain_query",
        description=("Explains the execution plan for a SQL query, showing how the database will execute it and provides detailed cost estimates."),
        annotations=ToolAnnotations(title="Explain Query", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )
    mcp.add_tool(
        postgres_analyze_workload_indexes,
        name="postgres_analyze_workload_indexes",
        description="Analyze frequently executed queries in the database and recommend optimal indexes",
        annotations=ToolAnnotations(title="Analyze Workload Indexes", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )
    mcp.add_tool(
        postgres_analyze_query_indexes,
        name="postgres_analyze_query_indexes",
        description="Analyze a list of (up to 10) SQL queries and recommend optimal indexes",
        annotations=ToolAnnotations(title="Analyze Query Indexes", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )
    mcp.add_tool(
        postgres_analyze_db_health,
        name="postgres_analyze_db_health",
        description=(
            "Analyzes database health. Here are the available health checks:\n"
            "- index - checks for invalid, duplicate, and bloated indexes\n"
            "- connection - checks the number of connection and their utilization\n"
            "- vacuum - checks vacuum health for transaction id wraparound\n"
            "- sequence - checks sequences at risk of exceeding their maximum value\n"
            "- replication - checks replication health including lag and slots\n"
            "- buffer - checks for buffer cache hit rates for indexes and tables\n"
            "- constraint - checks for invalid constraints\n"
            "- all - runs all checks\n"
            "You can optionally specify a single health check or a comma-separated list of health checks. "
            "The default is 'all' checks."
        ),
        annotations=ToolAnnotations(title="Analyze Database Health", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )
    mcp.add_tool(
        postgres_get_top_queries,
        name="postgres_get_top_queries",
        description=f"Reports the slowest or most resource-intensive queries using data from the '{PG_STAT_STATEMENTS}' extension.",
        annotations=ToolAnnotations(title="Get Top Queries", **_READONLY_ANNOTATIONS.model_dump(exclude={"title"})),
    )


_register_readonly_tools()

# ---------------------------------------------------------------------------
# Backward-compatible re-exports so existing tests using
#   ``from postgres_mcp.server import X``
# continue to work without changes.
# ---------------------------------------------------------------------------

# Re-export moved names at module level.  The old ``@mcp.tool()`` decorator
# typed these as ``Callable[..., Any]``; using ``Any`` here preserves that
# behaviour so existing tests and call-sites don't see new type errors.
list_schemas: Any = postgres_list_schemas
list_objects: Any = postgres_list_objects
get_object_details: Any = postgres_get_object_details
explain_query: Any = postgres_explain_query
execute_sql: Any = postgres_execute_sql
analyze_workload_indexes: Any = postgres_analyze_workload_indexes
analyze_query_indexes: Any = postgres_analyze_query_indexes
analyze_db_health: Any = postgres_analyze_db_health
get_top_queries: Any = postgres_get_top_queries

# Re-export state/helpers so ``from postgres_mcp.server import AccessMode`` etc. still works
db_connection = state.db_connection
current_access_mode = state.current_access_mode
shutdown_in_progress = state.shutdown_in_progress

__all__ = [
    "AccessMode",
    "ResponseType",
    "format_error_response",
    "format_text_response",
    "get_sql_driver",
    "main",
    "mcp",
    "shutdown",
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="PostgreSQL MCP Server")
    parser.add_argument("database_url", help="Database connection URL", nargs="?")
    parser.add_argument(
        "--access-mode",
        type=str,
        choices=[mode.value for mode in AccessMode],
        default=AccessMode.UNRESTRICTED.value,
        help="Set SQL access mode: unrestricted (unrestricted) or restricted (read-only with protections)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Select MCP transport: stdio (default), sse, or streamable-http",
    )
    parser.add_argument("--sse-host", type=str, default="localhost", help="Host to bind SSE server to (default: localhost)")
    parser.add_argument("--sse-port", type=int, default=8000, help="Port for SSE server (default: 8000)")
    parser.add_argument(
        "--streamable-http-host",
        type=str,
        default="localhost",
        help="Host to bind streamable HTTP server to (default: localhost)",
    )
    parser.add_argument(
        "--streamable-http-port",
        type=int,
        default=8000,
        help="Port for streamable HTTP server (default: 8000)",
    )

    args = parser.parse_args()

    state.current_access_mode = AccessMode(args.access_mode)

    # Register execute_sql with annotations appropriate to the access mode
    if state.current_access_mode == AccessMode.UNRESTRICTED:
        mcp.add_tool(
            postgres_execute_sql,
            name="postgres_execute_sql",
            description="Execute any SQL query",
            annotations=ToolAnnotations(
                title="Execute SQL",
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=False,
            ),
        )
    else:
        mcp.add_tool(
            postgres_execute_sql,
            name="postgres_execute_sql",
            description="Execute a read-only SQL query",
            annotations=ToolAnnotations(
                title="Execute SQL (Read-Only)",
                **_READONLY_ANNOTATIONS.model_dump(exclude={"title"}),
            ),
        )

    logger.info(f"Starting PostgreSQL MCP Server in {state.current_access_mode.upper()} mode")

    database_url = os.environ.get("DATABASE_URI", args.database_url)

    if not database_url:
        raise ValueError(
            "Error: No database URL provided. Please specify via 'DATABASE_URI' environment variable or command-line argument.",
        )

    try:
        await state.db_connection.pool_connect(database_url)
        logger.info("Successfully connected to database and initialized connection pool")
    except Exception as e:
        logger.warning(f"Could not connect to database: {obfuscate_password(str(e))}")
        logger.warning("The MCP server will start but database operations will fail until a valid connection is established.")

    try:
        loop = asyncio.get_running_loop()
        signals = (signal.SIGTERM, signal.SIGINT)
        for s in signals:
            loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(s)))
    except NotImplementedError:
        logger.warning("Signal handling not supported on Windows")

    if args.transport == "stdio":
        await mcp.run_stdio_async()
    elif args.transport == "sse":
        mcp.settings.host = args.sse_host
        mcp.settings.port = args.sse_port
        await mcp.run_sse_async()
    elif args.transport == "streamable-http":
        mcp.settings.host = args.streamable_http_host
        mcp.settings.port = args.streamable_http_port
        await mcp.run_streamable_http_async()


async def shutdown(sig=None) -> None:
    """Clean shutdown of the server."""
    if state.shutdown_in_progress:
        logger.warning("Forcing immediate exit")
        sys.exit(1)

    state.shutdown_in_progress = True

    if sig:
        logger.info(f"Received exit signal {sig.name}")

    try:
        await state.db_connection.close()
        logger.info("Closed database connections")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")

    sys.exit(128 + sig if sig is not None else 0)
