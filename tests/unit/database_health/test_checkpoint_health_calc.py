from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from postgres_mcp.database_health.checkpoint_health_calc import CheckpointHealthCalc


class MockCell:
    def __init__(self, data):
        self.cells = data


@pytest.mark.asyncio
async def test_checkpoint_health_unavailable_without_view(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return False

    monkeypatch.setattr(
        "postgres_mcp.database_health.checkpoint_health_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=None)
    calc = CheckpointHealthCalc(driver)

    result = await calc.checkpoint_health_check()
    assert result == "Checkpoint statistics unavailable (requires PostgreSQL 17 or later)."


@pytest.mark.asyncio
async def test_checkpoint_health_includes_pg18_columns(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, column_name):
        if column_name == "num_timed":
            return True
        if column_name in {"num_done", "slru_written"}:
            return True
        return False

    monkeypatch.setattr(
        "postgres_mcp.database_health.checkpoint_health_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(
        return_value=[
            MockCell(
                {
                    "num_timed": 10,
                    "num_requested": 2,
                    "restartpoints_timed": 3,
                    "restartpoints_req": 1,
                    "restartpoints_done": 4,
                    "write_time": 25.5,
                    "sync_time": 6.25,
                    "buffers_written": 1024,
                    "num_done": 12,
                    "slru_written": 8,
                    "stats_reset": "2026-02-16 10:00:00+00",
                }
            )
        ]
    )
    calc = CheckpointHealthCalc(driver)

    result = await calc.checkpoint_health_check()
    assert "Checkpoints: timed=10, requested=2, done=12" in result
    assert "Restartpoints: timed=3, requested=1, done=4" in result
    assert "Checkpoint I/O time: write=25.5 ms, sync=6.2 ms" in result
    assert "Buffers written: shared=1024, slru=8" in result
    assert "Stats reset at: 2026-02-16 10:00:00+00" in result
