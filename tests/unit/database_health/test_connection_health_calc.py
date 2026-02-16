from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from postgres_mcp.database_health.connection_health_calc import ConnectionHealthCalc


class MockCell:
    def __init__(self, data):
        self.cells = data


@pytest.mark.asyncio
async def test_connection_health_includes_wait_event_context(monkeypatch):
    async def fake_has_view_column(_driver, schema, view_name, column_name):
        return schema == "pg_catalog" and view_name == "pg_wait_events" and column_name == "name"

    monkeypatch.setattr(
        "postgres_mcp.database_health.connection_health_calc.has_view_column",
        fake_has_view_column,
    )

    async def side_effect(query):
        if "LEFT JOIN pg_catalog.pg_wait_events" in query:
            return [
                MockCell(
                    {
                        "wait_event_type": "Lock",
                        "wait_event": "transactionid",
                        "wait_event_description": "Waiting for transaction id lock",
                        "count": 120,
                    }
                )
            ]
        if "WHERE state = 'idle in transaction'" in query and "COUNT(*)" in query:
            return [MockCell({"count": 120})]
        if "FROM pg_stat_activity" in query and "COUNT(*)" in query:
            return [MockCell({"count": 140})]
        return None

    driver = MagicMock()
    driver.execute_query = AsyncMock(side_effect=side_effect)
    calc = ConnectionHealthCalc(driver, max_total_connections=500, max_idle_connections=100)

    result = await calc.connection_health_check()
    assert "High number of connections idle in transaction: 120" in result
    assert "Idle in transaction wait events:" in result
    assert "Lock:transactionid (count=120)" in result


@pytest.mark.asyncio
async def test_connection_health_without_wait_events_view(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return False

    monkeypatch.setattr(
        "postgres_mcp.database_health.connection_health_calc.has_view_column",
        fake_has_view_column,
    )

    async def side_effect(query):
        if "WHERE state = 'idle in transaction'" in query and "COUNT(*)" in query:
            return [MockCell({"count": 120})]
        if "FROM pg_stat_activity" in query and "COUNT(*)" in query:
            return [MockCell({"count": 140})]
        return None

    driver = MagicMock()
    driver.execute_query = AsyncMock(side_effect=side_effect)
    calc = ConnectionHealthCalc(driver, max_total_connections=500, max_idle_connections=100)

    result = await calc.connection_health_check()
    assert result == "High number of connections idle in transaction: 120"
