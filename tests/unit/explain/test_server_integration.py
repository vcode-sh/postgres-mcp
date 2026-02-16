import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio

from postgres_mcp.artifacts import ExplainPlanArtifact
from postgres_mcp.server import explain_query


@pytest_asyncio.fixture
async def mock_safe_sql_driver():
    """Create a mock SafeSqlDriver for testing."""
    driver = MagicMock()
    return driver


@pytest.fixture
def mock_explain_plan_tool():
    """Create a mock ExplainPlanTool."""
    tool = MagicMock()
    tool.explain = AsyncMock()
    tool.explain_analyze = AsyncMock()
    tool.explain_with_hypothetical_indexes = AsyncMock()
    return tool


class MockCell:
    def __init__(self, data):
        self.cells = data


def _make_explain_mock(result_text: str) -> MagicMock:
    """Create a mock ExplainPlanArtifact with the given text."""
    artifact = MagicMock(spec=ExplainPlanArtifact)
    artifact.to_text.return_value = result_text
    return artifact


@pytest.mark.asyncio
async def test_explain_query_integration():
    """Test the entire explain_query tool end-to-end."""
    result_text = json.dumps({"Plan": {"Node Type": "Seq Scan"}})
    artifact = _make_explain_mock(result_text)

    with patch("postgres_mcp.tools.query_tools.get_sql_driver", new_callable=AsyncMock):
        with patch("postgres_mcp.tools.query_tools.ExplainPlanTool") as mock_tool:
            mock_tool.return_value.explain = AsyncMock(return_value=artifact)
            result = await explain_query("SELECT * FROM users", analyze=False, hypothetical_indexes=[])

            from mcp.types import CallToolResult
            from mcp.types import TextContent

            assert isinstance(result, CallToolResult)
            first_content = result.content[0]
            assert isinstance(first_content, TextContent)
            assert result_text in first_content.text


@pytest.mark.asyncio
async def test_explain_query_with_analyze_integration():
    """Test the explain_query tool with analyze=True."""
    result_text = json.dumps({"Plan": {"Node Type": "Seq Scan"}, "Execution Time": 1.23})
    artifact = _make_explain_mock(result_text)

    with patch("postgres_mcp.tools.query_tools.get_sql_driver", new_callable=AsyncMock):
        with patch("postgres_mcp.tools.query_tools.ExplainPlanTool") as mock_tool:
            mock_tool.return_value.explain_analyze = AsyncMock(return_value=artifact)
            result = await explain_query("SELECT * FROM users", analyze=True, hypothetical_indexes=[])

            from mcp.types import CallToolResult
            from mcp.types import TextContent

            assert isinstance(result, CallToolResult)
            first_content = result.content[0]
            assert isinstance(first_content, TextContent)
            assert result_text in first_content.text
            mock_tool.return_value.explain_analyze.assert_awaited_once_with(
                "SELECT * FROM users",
                include_memory=False,
                serialize=None,
            )


@pytest.mark.asyncio
async def test_explain_query_with_analyze_memory_and_serialize_integration():
    """Test serialize/include_memory pass-through for analyze mode."""
    result_text = json.dumps({"Plan": {"Node Type": "Seq Scan"}, "Execution Time": 1.23})
    artifact = _make_explain_mock(result_text)

    with patch("postgres_mcp.tools.query_tools.get_sql_driver", new_callable=AsyncMock):
        with patch("postgres_mcp.tools.query_tools.ExplainPlanTool") as mock_tool:
            mock_tool.return_value.explain_analyze = AsyncMock(return_value=artifact)
            result = await explain_query(
                "SELECT * FROM users",
                analyze=True,
                include_memory=True,
                serialize="binary",
                hypothetical_indexes=[],
            )

            from mcp.types import CallToolResult

            assert isinstance(result, CallToolResult)
            mock_tool.return_value.explain_analyze.assert_awaited_once_with(
                "SELECT * FROM users",
                include_memory=True,
                serialize="binary",
            )


@pytest.mark.asyncio
async def test_explain_query_with_hypothetical_indexes_integration():
    """Test the explain_query tool with hypothetical indexes."""
    result_text = json.dumps({"Plan": {"Node Type": "Index Scan"}})
    artifact = _make_explain_mock(result_text)

    test_sql = "SELECT * FROM users WHERE email = 'test@example.com'"
    test_indexes = [{"table": "users", "columns": ["email"]}]

    with patch("postgres_mcp.tools.query_tools.get_sql_driver", new_callable=AsyncMock):
        with patch("postgres_mcp.tools.query_tools.ExplainPlanTool") as mock_tool:
            mock_tool.return_value.explain_with_hypothetical_indexes = AsyncMock(return_value=artifact)
            with patch(
                "postgres_mcp.tools.query_tools.check_hypopg_installation_status",
                new_callable=AsyncMock,
                return_value=(True, ""),
            ):
                result = await explain_query(test_sql, analyze=False, hypothetical_indexes=test_indexes)

                from mcp.types import CallToolResult
                from mcp.types import TextContent

                assert isinstance(result, CallToolResult)
                first_content = result.content[0]
                assert isinstance(first_content, TextContent)
                assert result_text in first_content.text


@pytest.mark.asyncio
async def test_explain_query_missing_hypopg_integration():
    """Test the explain_query tool when hypopg extension is missing."""
    missing_ext_message = "The hypopg extension is required"

    test_sql = "SELECT * FROM users WHERE email = 'test@example.com'"
    test_indexes = [{"table": "users", "columns": ["email"]}]

    with patch("postgres_mcp.tools.query_tools.get_sql_driver", new_callable=AsyncMock):
        with patch("postgres_mcp.tools.query_tools.ExplainPlanTool"):
            with patch(
                "postgres_mcp.tools.query_tools.check_hypopg_installation_status",
                new_callable=AsyncMock,
                return_value=(False, missing_ext_message),
            ):
                result = await explain_query(test_sql, analyze=False, hypothetical_indexes=test_indexes)

                from mcp.types import CallToolResult
                from mcp.types import TextContent

                assert isinstance(result, CallToolResult)
                first_content = result.content[0]
                assert isinstance(first_content, TextContent)
                assert missing_ext_message in first_content.text


@pytest.mark.asyncio
async def test_explain_query_serialize_requires_analyze():
    """Serialize requires analyze=True."""
    result = await explain_query("SELECT 1", serialize="text")

    from mcp.types import CallToolResult
    from mcp.types import TextContent

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    first_content = result.content[0]
    assert isinstance(first_content, TextContent)
    assert "SERIALIZE requires analyze=True" in first_content.text


@pytest.mark.asyncio
async def test_explain_query_serialize_mode_validation():
    """Serialize accepts only text/binary."""
    result = await explain_query("SELECT 1", analyze=True, serialize="json")

    from mcp.types import CallToolResult
    from mcp.types import TextContent

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    first_content = result.content[0]
    assert isinstance(first_content, TextContent)
    assert "SERIALIZE must be either 'text' or 'binary'" in first_content.text


@pytest.mark.asyncio
async def test_explain_query_serialize_with_hypothetical_indexes_rejected():
    """Serialize cannot be used with hypothetical indexes."""
    test_indexes = [{"table": "users", "columns": ["email"]}]
    result = await explain_query(
        "SELECT * FROM users",
        analyze=True,
        serialize="text",
        hypothetical_indexes=test_indexes,
    )

    from mcp.types import CallToolResult
    from mcp.types import TextContent

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    first_content = result.content[0]
    assert isinstance(first_content, TextContent)
    assert "Cannot use analyze and hypothetical indexes together" in first_content.text


@pytest.mark.asyncio
async def test_explain_query_error_handling_integration():
    """Test the explain_query tool's error handling."""
    error_message = "Error executing query"

    with patch(
        "postgres_mcp.tools.query_tools.get_sql_driver",
        side_effect=Exception(error_message),
    ):
        result = await explain_query("INVALID SQL")

        from mcp.types import CallToolResult
        from mcp.types import TextContent

        assert isinstance(result, CallToolResult)
        assert result.isError is True
        first_content = result.content[0]
        assert isinstance(first_content, TextContent)
        assert error_message in first_content.text
