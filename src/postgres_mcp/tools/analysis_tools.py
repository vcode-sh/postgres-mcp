# ruff: noqa: B008
import logging
from typing import Literal

from mcp.types import CallToolResult
from pydantic import Field

from postgres_mcp.database_health import DatabaseHealthTool
from postgres_mcp.database_health import HealthType
from postgres_mcp.index.dta_calc import DatabaseTuningAdvisor
from postgres_mcp.index.index_opt_base import MAX_NUM_INDEX_TUNING_QUERIES
from postgres_mcp.index.llm_opt import LLMOptimizerTool
from postgres_mcp.index.presentation import TextPresentation
from postgres_mcp.sql import SqlDriver
from postgres_mcp.top_queries import TopQueriesCalc

from ._response import format_error_response
from ._response import format_text_response
from ._state import get_sql_driver

logger = logging.getLogger(__name__)


def _create_index_tool(sql_driver: SqlDriver, method: str) -> TextPresentation:
    """Create the appropriate index analysis tool based on the method."""
    if method == "dta":
        optimizer = DatabaseTuningAdvisor(sql_driver)
    else:
        optimizer = LLMOptimizerTool(sql_driver)
    return TextPresentation(sql_driver, optimizer)


async def postgres_analyze_workload_indexes(
    max_index_size_mb: int = Field(description="Max index size in MB", default=10000),
    method: Literal["dta", "llm"] = Field(description="Method to use for analysis", default="dta"),
) -> CallToolResult:
    """Analyze frequently executed queries in the database and recommend optimal indexes."""
    try:
        sql_driver = await get_sql_driver()
        dta_tool = _create_index_tool(sql_driver, method)
        result = await dta_tool.analyze_workload(max_index_size_mb=max_index_size_mb)
        return format_text_response(result)
    except Exception as e:
        logger.error(f"Error analyzing workload: {e}")
        return format_error_response(str(e))


async def postgres_analyze_query_indexes(
    queries: list[str] = Field(description="List of Query strings to analyze"),
    max_index_size_mb: int = Field(description="Max index size in MB", default=10000),
    method: Literal["dta", "llm"] = Field(description="Method to use for analysis", default="dta"),
) -> CallToolResult:
    """Analyze a list of SQL queries and recommend optimal indexes."""
    if len(queries) == 0:
        return format_error_response("Please provide a non-empty list of queries to analyze.")
    if len(queries) > MAX_NUM_INDEX_TUNING_QUERIES:
        return format_error_response(f"Please provide a list of up to {MAX_NUM_INDEX_TUNING_QUERIES} queries to analyze.")

    try:
        sql_driver = await get_sql_driver()
        dta_tool = _create_index_tool(sql_driver, method)
        result = await dta_tool.analyze_queries(queries=queries, max_index_size_mb=max_index_size_mb)
        return format_text_response(result)
    except Exception as e:
        logger.error(f"Error analyzing queries: {e}")
        return format_error_response(str(e))


async def postgres_analyze_db_health(
    health_type: str = Field(
        description=f"Optional. Valid values are: {', '.join(sorted([t.value for t in HealthType]))}.",
        default="all",
    ),
) -> CallToolResult:
    """Analyze database health for specified components."""
    health_tool = DatabaseHealthTool(await get_sql_driver())
    result = await health_tool.health(health_type=health_type)
    return format_text_response(result)


async def postgres_get_top_queries(
    sort_by: str = Field(
        description="Ranking criteria: 'total_time' for total execution time or 'mean_time' for mean execution time per call, or 'resources' "
        "for resource-intensive queries",
        default="resources",
    ),
    limit: int = Field(description="Number of queries to return when ranking based on mean_time or total_time", default=10),
) -> CallToolResult:
    """Reports the slowest or most resource-intensive queries using pg_stat_statements."""
    try:
        sql_driver = await get_sql_driver()
        top_queries_tool = TopQueriesCalc(sql_driver=sql_driver)

        if sort_by == "resources":
            result = await top_queries_tool.get_top_resource_queries()
            return format_text_response(result)
        elif sort_by == "mean_time" or sort_by == "total_time":
            result = await top_queries_tool.get_top_queries_by_time(limit=limit, sort_by="mean" if sort_by == "mean_time" else "total")
        else:
            return format_error_response("Invalid sort criteria. Please use 'resources' or 'mean_time' or 'total_time'.")
        return format_text_response(result)
    except Exception as e:
        logger.error(f"Error getting slow queries: {e}")
        return format_error_response(str(e))
