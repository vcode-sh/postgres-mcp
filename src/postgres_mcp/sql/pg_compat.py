"""PostgreSQL compatibility helpers shared across tools."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .safe_sql import SafeSqlDriver
from .sql_driver import SqlDriver

logger = logging.getLogger(__name__)

_SERVER_INFO_CACHE: dict[str, PgServerInfo] = {}
_COLUMN_CACHE: dict[tuple[str, str, str, str], bool] = {}


@dataclass(frozen=True)
class PgServerInfo:
    """Minimal server version information used by compatibility gates."""

    server_version_num: int
    major: int


@dataclass(frozen=True)
class PgStatStatementsColumns:
    """Version-aware and capability-aware projection for pg_stat_statements."""

    total_time: str
    mean_time: str
    stddev_time: str
    wal_bytes_select: str
    wal_bytes_frac: str
    stats_since_select: str
    minmax_stats_since_select: str
    local_blk_read_time_select: str
    local_blk_write_time_select: str
    parallel_workers_to_launch_select: str
    parallel_workers_launched_select: str
    wal_buffers_full_select: str


def reset_pg_compat_cache() -> None:
    """Reset version and capability caches. Primarily used by tests."""
    _SERVER_INFO_CACHE.clear()
    _COLUMN_CACHE.clear()


def _unwrap_sql_driver(sql_driver: SqlDriver) -> SqlDriver:
    """Return the underlying SqlDriver if wrapped (e.g., SafeSqlDriver)."""
    candidate = sql_driver
    seen = set()
    while id(candidate) not in seen:
        seen.add(id(candidate))
        nested = getattr(candidate, "__dict__", {}).get("sql_driver")
        if nested is None:
            break
        candidate = nested
    return candidate


def _cache_key(sql_driver: SqlDriver) -> str:
    """Create a stable-ish key scoped to an active connection target."""
    driver = _unwrap_sql_driver(sql_driver)

    conn = getattr(driver, "__dict__", {}).get("conn")
    if conn is not None:
        return f"conn:{id(conn)}"

    engine_url = getattr(driver, "__dict__", {}).get("engine_url")
    if isinstance(engine_url, str) and engine_url:
        return f"url:{engine_url}"

    return f"driver:{id(driver)}"


def _major_from_version_string(version_string: str) -> int:
    """Parse major version from server version string."""
    match = re.search(r"(\d+)", version_string)
    if not match:
        return 0
    return int(match.group(1))


async def get_server_info(sql_driver: SqlDriver) -> PgServerInfo:
    """Return cached server version info, preferring server_version_num."""
    key = _cache_key(sql_driver)
    cached = _SERVER_INFO_CACHE.get(key)
    if cached is not None:
        return cached

    version_num = 0
    major = 0

    try:
        rows = await sql_driver.execute_query("SHOW server_version_num")
        if rows:
            raw_value = rows[0].cells.get("server_version_num", 0)
            version_num = int(raw_value) if raw_value is not None else 0
            major = version_num // 10000 if version_num >= 10000 else version_num
    except Exception as e:
        logger.debug("Failed to read server_version_num, falling back to server_version: %s", e)

    if major == 0:
        try:
            rows = await sql_driver.execute_query("SHOW server_version")
            if rows:
                raw_value = str(rows[0].cells.get("server_version", ""))
                major = _major_from_version_string(raw_value)
                version_num = major * 10000 if major > 0 else 0
        except Exception as e:
            raise ValueError("Error determining PostgreSQL server version") from e

    info = PgServerInfo(server_version_num=version_num, major=major)
    _SERVER_INFO_CACHE[key] = info
    return info


async def has_view_column(sql_driver: SqlDriver, schema: str, view_name: str, column_name: str) -> bool:
    """Check whether a specific view/table column exists."""
    key = (_cache_key(sql_driver), schema, view_name, column_name)
    cached = _COLUMN_CACHE.get(key)
    if cached is not None:
        return cached

    rows = await SafeSqlDriver.execute_param_query(
        sql_driver,
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = {}
              AND table_name = {}
              AND column_name = {}
        ) AS has_column
        """,
        [schema, view_name, column_name],
    )

    has_column = bool(rows and rows[0].cells.get("has_column"))
    _COLUMN_CACHE[key] = has_column
    return has_column


async def has_pg_stat_statements_column(sql_driver: SqlDriver, column_name: str) -> bool:
    """Check whether pg_stat_statements exposes a given column."""
    key = (_cache_key(sql_driver), "*", "pg_stat_statements", column_name)
    cached = _COLUMN_CACHE.get(key)
    if cached is not None:
        return cached

    rows = await SafeSqlDriver.execute_param_query(
        sql_driver,
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'pg_stat_statements'
              AND n.nspname NOT IN ('pg_toast')
              AND a.attname = {}
              AND NOT a.attisdropped
        ) AS has_column
        """,
        [column_name],
    )

    has_column = bool(rows and rows[0].cells.get("has_column"))
    _COLUMN_CACHE[key] = has_column
    return has_column


async def get_pg_stat_statements_columns(sql_driver: SqlDriver) -> PgStatStatementsColumns:
    """Return capability-aware pg_stat_statements projection details."""
    total_time = "total_exec_time" if await has_pg_stat_statements_column(sql_driver, "total_exec_time") else "total_time"
    mean_time = "mean_exec_time" if await has_pg_stat_statements_column(sql_driver, "mean_exec_time") else "mean_time"
    stddev_time = "stddev_exec_time" if await has_pg_stat_statements_column(sql_driver, "stddev_exec_time") else "stddev_time"
    has_wal_bytes = await has_pg_stat_statements_column(sql_driver, "wal_bytes")

    def optional_select(column: str, fallback_cast: str) -> str:
        return f"{column} AS {column}" if column_presence[column] else f"NULL::{fallback_cast} AS {column}"

    column_presence = {
        "stats_since": await has_pg_stat_statements_column(sql_driver, "stats_since"),
        "minmax_stats_since": await has_pg_stat_statements_column(sql_driver, "minmax_stats_since"),
        "local_blk_read_time": await has_pg_stat_statements_column(sql_driver, "local_blk_read_time"),
        "local_blk_write_time": await has_pg_stat_statements_column(sql_driver, "local_blk_write_time"),
        "parallel_workers_to_launch": await has_pg_stat_statements_column(sql_driver, "parallel_workers_to_launch"),
        "parallel_workers_launched": await has_pg_stat_statements_column(sql_driver, "parallel_workers_launched"),
        "wal_buffers_full": await has_pg_stat_statements_column(sql_driver, "wal_buffers_full"),
    }

    return PgStatStatementsColumns(
        total_time=total_time,
        mean_time=mean_time,
        stddev_time=stddev_time,
        wal_bytes_select="wal_bytes AS wal_bytes" if has_wal_bytes else "0::numeric AS wal_bytes",
        wal_bytes_frac=(
            "wal_bytes / NULLIF(SUM(wal_bytes) OVER (), 0) AS total_wal_bytes_frac"
            if has_wal_bytes
            else "0::double precision AS total_wal_bytes_frac"
        ),
        stats_since_select=optional_select("stats_since", "timestamptz"),
        minmax_stats_since_select=optional_select("minmax_stats_since", "timestamptz"),
        local_blk_read_time_select=optional_select("local_blk_read_time", "double precision"),
        local_blk_write_time_select=optional_select("local_blk_write_time", "double precision"),
        parallel_workers_to_launch_select=optional_select("parallel_workers_to_launch", "bigint"),
        parallel_workers_launched_select=optional_select("parallel_workers_launched", "bigint"),
        wal_buffers_full_select=optional_select("wal_buffers_full", "bigint"),
    )
