from typing import Any
from typing import cast
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from postgres_mcp.database_health.vacuum_health_calc import VacuumHealthCalc


class MockCell:
    def __init__(self, data):
        self.cells = data


@pytest.mark.asyncio
async def test_vacuum_health_includes_timing_summary(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return True

    monkeypatch.setattr(
        "postgres_mcp.database_health.vacuum_health_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(
        return_value=[
            MockCell(
                {
                    "total_vacuum_time": 12.5,
                    "total_autovacuum_time": 33.0,
                    "total_analyze_time": 5.0,
                    "total_autoanalyze_time": 8.25,
                }
            )
        ]
    )

    calc = VacuumHealthCalc(driver)
    cast(Any, calc)._get_transaction_id_metrics = AsyncMock(return_value=[])
    result = await calc.transaction_id_danger_check()

    assert "No tables found with transaction ID wraparound danger." in result
    assert "Vacuum timing totals (ms):" in result
    assert "manual vacuum=12.5" in result
    assert "autovacuum=33.0" in result


@pytest.mark.asyncio
async def test_vacuum_health_without_timing_columns(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return False

    monkeypatch.setattr(
        "postgres_mcp.database_health.vacuum_health_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=None)

    calc = VacuumHealthCalc(driver)
    cast(Any, calc)._get_transaction_id_metrics = AsyncMock(return_value=[])
    result = await calc.transaction_id_danger_check()
    assert result == "No tables found with transaction ID wraparound danger."
