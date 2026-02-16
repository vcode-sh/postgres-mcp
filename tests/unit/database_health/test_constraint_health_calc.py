from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from postgres_mcp.database_health.constraint_health_calc import ConstraintHealthCalc


class MockCell:
    def __init__(self, data):
        self.cells = data


@pytest.mark.asyncio
async def test_invalid_constraint_message_without_conenforced(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return False

    monkeypatch.setattr(
        "postgres_mcp.database_health.constraint_health_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(
        return_value=[
            MockCell(
                {
                    "schema": "public",
                    "table": "orders",
                    "name": "orders_customer_fk",
                    "referenced_schema": "public",
                    "referenced_table": "customers",
                    "validated": False,
                    "enforced": True,
                }
            )
        ]
    )

    calc = ConstraintHealthCalc(driver)
    result = await calc.invalid_constraints_check()
    assert "Constraint issues found:" in result
    assert "referencing 'public.customers' is invalid" in result


@pytest.mark.asyncio
async def test_not_enforced_constraint_message(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return True

    monkeypatch.setattr(
        "postgres_mcp.database_health.constraint_health_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(
        return_value=[
            MockCell(
                {
                    "schema": "public",
                    "table": "orders",
                    "name": "orders_total_check",
                    "referenced_schema": None,
                    "referenced_table": None,
                    "validated": True,
                    "enforced": False,
                }
            )
        ]
    )

    calc = ConstraintHealthCalc(driver)
    result = await calc.invalid_constraints_check()
    assert "orders_total_check" in result
    assert "is not enforced" in result


@pytest.mark.asyncio
async def test_constraint_health_no_issues(monkeypatch):
    async def fake_has_view_column(_driver, _schema, _view_name, _column_name):
        return True

    monkeypatch.setattr(
        "postgres_mcp.database_health.constraint_health_calc.has_view_column",
        fake_has_view_column,
    )

    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=[])
    calc = ConstraintHealthCalc(driver)

    result = await calc.invalid_constraints_check()
    assert result == "No invalid or not-enforced constraints found."
