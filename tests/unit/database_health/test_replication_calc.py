from typing import Any
from typing import cast
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from postgres_mcp.database_health.replication_calc import ReplicationCalc
from postgres_mcp.database_health.replication_calc import ReplicationMetrics
from postgres_mcp.database_health.replication_calc import ReplicationSlot


class MockCell:
    def __init__(self, data):
        self.cells = data


@pytest.mark.asyncio
async def test_replication_slots_include_pg17_fields(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return True

    monkeypatch.setattr(
        "postgres_mcp.database_health.replication_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(
        return_value=[
            MockCell(
                {
                    "slot_name": "slot_a",
                    "database": "postgres",
                    "active": False,
                    "invalidation_reason": "wal_removed",
                    "inactive_since": "2026-02-16 08:00:00+00",
                    "failover": True,
                    "synced": False,
                }
            )
        ]
    )

    calc = ReplicationCalc(driver)
    raw_calc = cast(Any, calc)
    raw_calc._server_version = 170000
    slots = await raw_calc._get_replication_slots()

    assert len(slots) == 1
    slot = slots[0]
    assert slot.slot_name == "slot_a"
    assert slot.invalidation_reason == "wal_removed"
    assert slot.inactive_since == "2026-02-16 08:00:00+00"
    assert slot.failover is True
    assert slot.synced is False


@pytest.mark.asyncio
async def test_replication_health_formats_slot_details():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=[])
    calc = ReplicationCalc(driver)
    raw_calc = cast(Any, calc)
    raw_calc._get_replication_metrics = AsyncMock(
        return_value=ReplicationMetrics(
            is_replica=False,
            replication_lag_seconds=None,
            is_replicating=True,
            replication_slots=[
                ReplicationSlot(
                    slot_name="slot_a",
                    database="postgres",
                    active=False,
                    invalidation_reason="wal_removed",
                    inactive_since="2026-02-16 08:00:00+00",
                    failover=True,
                    synced=False,
                )
            ],
        )
    )

    result = await calc.replication_health_check()
    assert "Inactive replication slots:" in result
    assert "slot_a (database: postgres)" in result
    assert "failover=True" in result
    assert "synced=False" in result
    assert "invalidation_reason=wal_removed" in result
