from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from postgres_mcp.sql import SqlDriver
from postgres_mcp.sql.pg_compat import get_pg_stat_statements_columns
from postgres_mcp.sql.pg_compat import get_server_info
from postgres_mcp.sql.pg_compat import reset_pg_compat_cache


class MockSqlRowResult:
    def __init__(self, cells):
        self.cells = cells


@pytest.fixture(autouse=True)
def clear_pg_compat_cache():
    reset_pg_compat_cache()
    yield
    reset_pg_compat_cache()


@pytest.mark.asyncio
async def test_get_server_info_prefers_server_version_num():
    driver = MagicMock(spec=SqlDriver)
    driver.execute_query = AsyncMock(return_value=[MockSqlRowResult({"server_version_num": "180001"})])

    info = await get_server_info(driver)
    assert info.server_version_num == 180001
    assert info.major == 18


@pytest.mark.asyncio
async def test_get_server_info_falls_back_to_server_version():
    driver = MagicMock(spec=SqlDriver)

    async def side_effect(query, *args, **kwargs):
        if query == "SHOW server_version_num":
            raise ValueError("not available")
        if query == "SHOW server_version":
            return [MockSqlRowResult({"server_version": "17.5 (Debian 17.5-1.pgdg120+1)"})]
        return None

    driver.execute_query = AsyncMock(side_effect=side_effect)

    info = await get_server_info(driver)
    assert info.server_version_num == 170000
    assert info.major == 17


@pytest.mark.asyncio
async def test_get_pg_stat_statements_columns_handles_optional_columns():
    driver = MagicMock(spec=SqlDriver)
    driver.execute_query = AsyncMock(return_value=[MockSqlRowResult({"server_version_num": "180001"})])

    availability = {
        "total_exec_time": True,
        "mean_exec_time": True,
        "stddev_exec_time": True,
        "wal_bytes": True,
        "stats_since": True,
        "minmax_stats_since": True,
        "local_blk_read_time": True,
        "local_blk_write_time": True,
        "parallel_workers_to_launch": True,
        "parallel_workers_launched": True,
        "wal_buffers_full": True,
    }

    with patch("postgres_mcp.sql.pg_compat.has_pg_stat_statements_column", AsyncMock(side_effect=lambda _d, c: availability[c])):
        cols = await get_pg_stat_statements_columns(driver)

    assert cols.total_time == "total_exec_time"
    assert cols.mean_time == "mean_exec_time"
    assert cols.stddev_time == "stddev_exec_time"
    assert cols.wal_bytes_select == "wal_bytes AS wal_bytes"
    assert cols.stats_since_select == "stats_since AS stats_since"
    assert cols.parallel_workers_to_launch_select == "parallel_workers_to_launch AS parallel_workers_to_launch"
