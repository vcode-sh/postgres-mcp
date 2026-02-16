# ruff: noqa: B008
import logging
from typing import Any
from typing import Optional

from mcp.types import CallToolResult
from pydantic import Field
from pydantic.fields import FieldInfo

from postgres_mcp.artifacts import ErrorResult
from postgres_mcp.artifacts import ExplainPlanArtifact
from postgres_mcp.explain import ExplainPlanTool
from postgres_mcp.sql import check_hypopg_installation_status

from ._response import format_error_response
from ._response import format_text_response
from ._state import get_sql_driver

logger = logging.getLogger(__name__)


def _resolve_field_default(value: Any) -> Any:
    """Handle direct Python calls where pydantic Field defaults can leak through."""
    if isinstance(value, FieldInfo):
        return value.default
    return value


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
    include_memory: bool = Field(
        description="Include planner memory usage in EXPLAIN output (PostgreSQL 17+).",
        default=False,
    ),
    serialize: Optional[str] = Field(
        description="Serialization mode for EXPLAIN ANALYZE (PostgreSQL 17+): 'text' or 'binary'. Requires analyze=True.",
        default=None,
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
        analyze_value = _resolve_field_default(analyze)
        include_memory_value = _resolve_field_default(include_memory)
        serialize_value = _resolve_field_default(serialize)
        hypothetical_indexes_value = _resolve_field_default(hypothetical_indexes)

        if not isinstance(analyze_value, bool):
            return format_error_response("analyze must be a boolean")
        if not isinstance(include_memory_value, bool):
            return format_error_response("include_memory must be a boolean")
        if serialize_value is not None and not isinstance(serialize_value, str):
            return format_error_response("serialize must be a string when provided")
        if hypothetical_indexes_value is None:
            hypothetical_indexes_value = []
        if not isinstance(hypothetical_indexes_value, list):
            return format_error_response("hypothetical_indexes must be a list")

        serialize_mode = serialize_value.lower() if isinstance(serialize_value, str) else None

        if serialize_mode and serialize_mode not in {"text", "binary"}:
            return format_error_response("SERIALIZE must be either 'text' or 'binary'")
        if serialize_mode and not analyze_value:
            return format_error_response("SERIALIZE requires analyze=True")

        result: ExplainPlanArtifact | ErrorResult | None = None
        sql_driver = await get_sql_driver()
        explain_tool = ExplainPlanTool(sql_driver=sql_driver)

        if hypothetical_indexes_value and len(hypothetical_indexes_value) > 0:
            if analyze_value:
                return format_error_response("Cannot use analyze and hypothetical indexes together")
            if serialize_mode:
                return format_error_response("Cannot use serialize with hypothetical indexes")

            is_hypopg_installed, hypopg_message = await check_hypopg_installation_status(sql_driver)
            if not is_hypopg_installed:
                return format_text_response(hypopg_message)

            result = await explain_tool.explain_with_hypothetical_indexes(
                sql,
                hypothetical_indexes_value,
                include_memory=include_memory_value,
            )
        elif analyze_value:
            result = await explain_tool.explain_analyze(
                sql,
                include_memory=include_memory_value,
                serialize=serialize_mode,
            )
        else:
            result = await explain_tool.explain(
                sql,
                include_memory=include_memory_value,
                serialize=serialize_mode,
            )

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
