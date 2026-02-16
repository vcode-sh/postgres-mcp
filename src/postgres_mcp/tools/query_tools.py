# ruff: noqa: B008
import logging
from typing import Any
from typing import Optional

from mcp.types import CallToolResult
from pydantic import Field

from postgres_mcp.artifacts import ErrorResult
from postgres_mcp.artifacts import ExplainPlanArtifact
from postgres_mcp.explain import ExplainPlanTool
from postgres_mcp.sql import check_hypopg_installation_status

from ._response import format_error_response
from ._response import format_text_response
from ._state import get_sql_driver

logger = logging.getLogger(__name__)


async def postgres_execute_sql(
    sql: str = Field(description="SQL to run"),
    offset: Optional[int] = Field(description="Number of rows to skip (for pagination)", default=None),
    limit: Optional[int] = Field(description="Maximum number of rows to return (for pagination)", default=None),
) -> CallToolResult:
    """Executes a SQL query against the database."""
    try:
        sql_driver = await get_sql_driver()
        rows = await sql_driver.execute_query(sql)  # type: ignore[arg-type]
        if rows is None:
            return format_text_response("No results")
        result = [r.cells for r in rows]
        if offset is not None:
            result = result[offset:]
        if limit is not None:
            result = result[:limit]
        return format_text_response(result)
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return format_error_response(str(e))


async def postgres_explain_query(
    sql: str = Field(description="SQL query to explain"),
    analyze: bool = Field(
        description="When True, actually runs the query to show real execution statistics instead of estimates. "
        "Takes longer but provides more accurate information.",
        default=False,
    ),
    hypothetical_indexes: list[dict[str, Any]] = Field(
        description="""A list of hypothetical indexes to simulate. Each index must be a dictionary with these keys:
    - 'table': The table name to add the index to (e.g., 'users')
    - 'columns': List of column names to include in the index (e.g., ['email'] or ['last_name', 'first_name'])
    - 'using': Optional index method (default: 'btree', other options include 'hash', 'gist', etc.)

Examples: [
    {"table": "users", "columns": ["email"], "using": "btree"},
    {"table": "orders", "columns": ["user_id", "created_at"]}
]
If there is no hypothetical index, you can pass an empty list.""",
        default=[],
    ),
) -> CallToolResult:
    """Explains the execution plan for a SQL query."""
    try:
        sql_driver = await get_sql_driver()
        explain_tool = ExplainPlanTool(sql_driver=sql_driver)
        result: ExplainPlanArtifact | ErrorResult | None = None

        if hypothetical_indexes and len(hypothetical_indexes) > 0:
            if analyze:
                return format_error_response("Cannot use analyze and hypothetical indexes together")

            is_hypopg_installed, hypopg_message = await check_hypopg_installation_status(sql_driver)
            if not is_hypopg_installed:
                return format_text_response(hypopg_message)

            result = await explain_tool.explain_with_hypothetical_indexes(sql, hypothetical_indexes)
        elif analyze:
            result = await explain_tool.explain_analyze(sql)
        else:
            result = await explain_tool.explain(sql)

        if result and isinstance(result, ExplainPlanArtifact):
            return format_text_response(result.to_text())
        else:
            error_message = "Error processing explain plan"
            if isinstance(result, ErrorResult):
                error_message = result.to_text()
            return format_error_response(error_message)
    except Exception as e:
        logger.error(f"Error explaining query: {e}")
        return format_error_response(str(e))
