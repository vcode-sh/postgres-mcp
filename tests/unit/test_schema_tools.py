import json
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from postgres_mcp.tools.schema_tools import postgres_get_object_details


class MockCell:
    def __init__(self, data):
        self.cells = data


def _parse_json_payload(result) -> dict[str, Any]:
    assert result.content
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_get_object_details_includes_generated_and_constraint_flags():
    driver = MagicMock()

    async def param_side_effect(_sql_driver, query, params):
        if "FROM information_schema.columns" in query:
            return [
                MockCell(
                    {
                        "column_name": "id",
                        "data_type": "integer",
                        "is_nullable": "NO",
                        "column_default": None,
                        "is_generated": "NEVER",
                        "generation_expression": None,
                    }
                ),
                MockCell(
                    {
                        "column_name": "slug",
                        "data_type": "text",
                        "is_nullable": "YES",
                        "column_default": None,
                        "is_generated": "ALWAYS",
                        "generation_expression": "lower(id::text)",
                    }
                ),
            ]
        if "FROM information_schema.table_constraints AS tc" in query:
            return [
                MockCell(
                    {
                        "constraint_name": "products_pkey",
                        "constraint_type": "PRIMARY KEY",
                        "column_name": "id",
                    }
                )
            ]
        if "FROM pg_catalog.pg_constraint con" in query:
            return [
                MockCell(
                    {
                        "constraint_name": "products_pkey",
                        "is_validated": True,
                        "is_enforced": True,
                    }
                )
            ]
        if "FROM pg_indexes" in query:
            return [MockCell({"indexname": "products_pkey", "indexdef": "CREATE UNIQUE INDEX products_pkey ON products USING btree (id)"})]
        raise AssertionError(f"Unexpected query: {query}")

    with patch("postgres_mcp.tools.schema_tools.get_sql_driver", new=AsyncMock(return_value=driver)):
        with patch(
            "postgres_mcp.tools.schema_tools.SafeSqlDriver.execute_param_query",
            new=AsyncMock(side_effect=param_side_effect),
        ):
            with patch("postgres_mcp.tools.schema_tools.has_view_column", new=AsyncMock(return_value=True)):
                result = await postgres_get_object_details("public", "products", "table")

    payload = _parse_json_payload(result)
    assert payload["columns"][1]["is_generated"] == "ALWAYS"
    assert payload["columns"][1]["generation_expression"] == "lower(id::text)"
    assert payload["constraints"][0]["is_validated"] is True
    assert payload["constraints"][0]["is_enforced"] is True


@pytest.mark.asyncio
async def test_get_object_details_skips_is_enforced_when_not_supported():
    driver = MagicMock()

    async def param_side_effect(_sql_driver, query, params):
        if "FROM information_schema.columns" in query:
            return [
                MockCell(
                    {
                        "column_name": "id",
                        "data_type": "integer",
                        "is_nullable": "NO",
                        "column_default": None,
                        "is_generated": "NEVER",
                        "generation_expression": None,
                    }
                )
            ]
        if "FROM information_schema.table_constraints AS tc" in query:
            return [
                MockCell(
                    {
                        "constraint_name": "products_pkey",
                        "constraint_type": "PRIMARY KEY",
                        "column_name": "id",
                    }
                )
            ]
        if "FROM pg_catalog.pg_constraint con" in query:
            return [
                MockCell(
                    {
                        "constraint_name": "products_pkey",
                        "is_validated": True,
                        "is_enforced": True,
                    }
                )
            ]
        if "FROM pg_indexes" in query:
            return []
        raise AssertionError(f"Unexpected query: {query}")

    with patch("postgres_mcp.tools.schema_tools.get_sql_driver", new=AsyncMock(return_value=driver)):
        with patch(
            "postgres_mcp.tools.schema_tools.SafeSqlDriver.execute_param_query",
            new=AsyncMock(side_effect=param_side_effect),
        ):
            with patch("postgres_mcp.tools.schema_tools.has_view_column", new=AsyncMock(return_value=False)):
                result = await postgres_get_object_details("public", "products", "table")

    payload = _parse_json_payload(result)
    assert payload["constraints"][0]["is_validated"] is True
    assert "is_enforced" not in payload["constraints"][0]
