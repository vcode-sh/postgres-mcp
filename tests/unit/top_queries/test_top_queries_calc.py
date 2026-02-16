from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

import postgres_mcp.top_queries.top_queries_calc as top_queries_module
from postgres_mcp.sql import PgStatStatementsColumns
from postgres_mcp.sql import SqlDriver
from postgres_mcp.sql.extension_utils import ExtensionStatus
from postgres_mcp.top_queries import TopQueriesCalc


class MockSqlRowResult:
    def __init__(self, cells):
        self.cells = cells


def _columns_for_pg12() -> PgStatStatementsColumns:
    return PgStatStatementsColumns(
        total_time="total_time",
        mean_time="mean_time",
        stddev_time="stddev_time",
        wal_bytes_select="0::numeric AS wal_bytes",
        wal_bytes_frac="0::double precision AS total_wal_bytes_frac",
        stats_since_select="NULL::timestamptz AS stats_since",
        minmax_stats_since_select="NULL::timestamptz AS minmax_stats_since",
        local_blk_read_time_select="NULL::double precision AS local_blk_read_time",
        local_blk_write_time_select="NULL::double precision AS local_blk_write_time",
        parallel_workers_to_launch_select="NULL::bigint AS parallel_workers_to_launch",
        parallel_workers_launched_select="NULL::bigint AS parallel_workers_launched",
        wal_buffers_full_select="NULL::bigint AS wal_buffers_full",
    )


def _columns_for_pg13() -> PgStatStatementsColumns:
    return PgStatStatementsColumns(
        total_time="total_exec_time",
        mean_time="mean_exec_time",
        stddev_time="stddev_exec_time",
        wal_bytes_select="wal_bytes AS wal_bytes",
        wal_bytes_frac="wal_bytes / NULLIF(SUM(wal_bytes) OVER (), 0) AS total_wal_bytes_frac",
        stats_since_select="NULL::timestamptz AS stats_since",
        minmax_stats_since_select="NULL::timestamptz AS minmax_stats_since",
        local_blk_read_time_select="NULL::double precision AS local_blk_read_time",
        local_blk_write_time_select="NULL::double precision AS local_blk_write_time",
        parallel_workers_to_launch_select="NULL::bigint AS parallel_workers_to_launch",
        parallel_workers_launched_select="NULL::bigint AS parallel_workers_launched",
        wal_buffers_full_select="NULL::bigint AS wal_buffers_full",
    )


@pytest.fixture
def mock_pg12_driver():
    """Create a mock for SqlDriver that simulates PostgreSQL 12 rows."""
    driver = MagicMock(spec=SqlDriver)
    mock_execute = AsyncMock()

    async def side_effect(query, *args, **kwargs):
        if "pg_stat_statements" in query:
            return [
                MockSqlRowResult(cells={"query": "SELECT * FROM users", "calls": 100, "total_time": 1000.0, "mean_time": 10.0, "rows": 1000}),
                MockSqlRowResult(cells={"query": "SELECT * FROM orders", "calls": 50, "total_time": 750.0, "mean_time": 15.0, "rows": 500}),
                MockSqlRowResult(cells={"query": "SELECT * FROM products", "calls": 200, "total_time": 500.0, "mean_time": 2.5, "rows": 2000}),
            ]
        return None

    mock_execute.side_effect = side_effect
    driver.execute_query = mock_execute
    return driver


@pytest.fixture
def mock_pg13_driver():
    """Create a mock for SqlDriver that simulates PostgreSQL 13 rows."""
    driver = MagicMock(spec=SqlDriver)
    mock_execute = AsyncMock()

    async def side_effect(query, *args, **kwargs):
        if "pg_stat_statements" in query:
            return [
                MockSqlRowResult(
                    cells={"query": "SELECT * FROM users", "calls": 100, "total_exec_time": 1000.0, "mean_exec_time": 10.0, "rows": 1000}
                ),
                MockSqlRowResult(
                    cells={"query": "SELECT * FROM orders", "calls": 50, "total_exec_time": 750.0, "mean_exec_time": 15.0, "rows": 500}
                ),
                MockSqlRowResult(
                    cells={"query": "SELECT * FROM products", "calls": 200, "total_exec_time": 500.0, "mean_exec_time": 2.5, "rows": 2000}
                ),
            ]
        return None

    mock_execute.side_effect = side_effect
    driver.execute_query = mock_execute
    return driver


@pytest.fixture
def mock_extension_installed():
    with patch.object(top_queries_module, "check_extension", autospec=True) as mock_check:
        mock_check.return_value = ExtensionStatus(
            is_installed=True,
            is_available=True,
            name="pg_stat_statements",
            message="Extension is installed",
            default_version="1.0",
        )
        yield mock_check


@pytest.fixture
def mock_extension_not_installed():
    with patch.object(top_queries_module, "check_extension", autospec=True) as mock_check:
        mock_check.return_value = ExtensionStatus(
            is_installed=False,
            is_available=True,
            name="pg_stat_statements",
            message="Extension not installed",
            default_version=None,
        )
        yield mock_check


@pytest.mark.asyncio
async def test_top_queries_pg12_total_sort(mock_pg12_driver, mock_extension_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg12_driver)
    with patch.object(top_queries_module, "get_pg_stat_statements_columns", AsyncMock(return_value=_columns_for_pg12())):
        result = await calc.get_top_queries_by_time(limit=3, sort_by="total")

    assert "Top 3 slowest queries by total execution time" in result
    assert "SELECT * FROM users" in result
    assert "ORDER BY total_time DESC" in str(mock_pg12_driver.execute_query.call_args)


@pytest.mark.asyncio
async def test_top_queries_pg12_mean_sort(mock_pg12_driver, mock_extension_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg12_driver)
    with patch.object(top_queries_module, "get_pg_stat_statements_columns", AsyncMock(return_value=_columns_for_pg12())):
        result = await calc.get_top_queries_by_time(limit=3, sort_by="mean")

    assert "Top 3 slowest queries by mean execution time per call" in result
    assert "SELECT * FROM orders" in result
    assert "ORDER BY mean_time DESC" in str(mock_pg12_driver.execute_query.call_args)


@pytest.mark.asyncio
async def test_top_queries_pg13_total_sort(mock_pg13_driver, mock_extension_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg13_driver)
    with patch.object(top_queries_module, "get_pg_stat_statements_columns", AsyncMock(return_value=_columns_for_pg13())):
        result = await calc.get_top_queries_by_time(limit=3, sort_by="total")

    assert "Top 3 slowest queries by total execution time" in result
    assert "SELECT * FROM users" in result
    assert "ORDER BY total_exec_time DESC" in str(mock_pg13_driver.execute_query.call_args)


@pytest.mark.asyncio
async def test_top_queries_pg13_mean_sort(mock_pg13_driver, mock_extension_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg13_driver)
    with patch.object(top_queries_module, "get_pg_stat_statements_columns", AsyncMock(return_value=_columns_for_pg13())):
        result = await calc.get_top_queries_by_time(limit=3, sort_by="mean")

    assert "Top 3 slowest queries by mean execution time per call" in result
    assert "SELECT * FROM orders" in result
    assert "ORDER BY mean_exec_time DESC" in str(mock_pg13_driver.execute_query.call_args)


@pytest.mark.asyncio
async def test_extension_not_installed(mock_pg13_driver, mock_extension_not_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg13_driver)
    result = await calc.get_top_queries_by_time(limit=3)
    assert "extension is required to report" in result
    assert "CREATE EXTENSION" in result
    mock_pg13_driver.execute_query.assert_not_called()


@pytest.mark.asyncio
async def test_error_handling(mock_pg13_driver, mock_extension_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg13_driver)
    with patch.object(top_queries_module, "get_pg_stat_statements_columns", AsyncMock(side_effect=Exception("Database error"))):
        result = await calc.get_top_queries_by_time(limit=3)
    assert "Error getting slow queries: Database error" in result


@pytest.mark.asyncio
async def test_resource_queries_pg12(mock_pg12_driver, mock_extension_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg12_driver)
    with patch.object(top_queries_module, "get_pg_stat_statements_columns", AsyncMock(return_value=_columns_for_pg12())):
        _result = await calc.get_top_resource_queries(frac_threshold=0.05)

    call_args = str(mock_pg12_driver.execute_query.call_args)
    assert "stddev_time AS stddev_exec_time" in call_args
    assert "total_time AS total_exec_time" in call_args
    assert "mean_time AS mean_exec_time" in call_args
    assert "0::numeric AS wal_bytes" in call_args
    assert "stats_since" in call_args


@pytest.mark.asyncio
async def test_resource_queries_pg13(mock_pg13_driver, mock_extension_installed):
    calc = TopQueriesCalc(sql_driver=mock_pg13_driver)
    with patch.object(top_queries_module, "get_pg_stat_statements_columns", AsyncMock(return_value=_columns_for_pg13())):
        _result = await calc.get_top_resource_queries(frac_threshold=0.05)

    call_args = str(mock_pg13_driver.execute_query.call_args)
    assert "stddev_exec_time" in call_args
    assert "total_exec_time" in call_args
    assert "mean_exec_time" in call_args
    assert "wal_bytes AS wal_bytes" in call_args
