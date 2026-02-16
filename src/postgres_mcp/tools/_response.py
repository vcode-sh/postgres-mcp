import json
from typing import Any

import mcp.types as types
from mcp.types import CallToolResult


def format_text_response(text: Any) -> CallToolResult:
    """Format a text response.

    Strings are passed through as-is. All other types are serialized to JSON
    with ``default=str`` so that objects like ``datetime`` are handled gracefully.
    """
    if isinstance(text, str):
        body = text
    else:
        body = json.dumps(text, indent=2, default=str)
    return CallToolResult(
        content=[types.TextContent(type="text", text=body)],
    )


def format_error_response(error: str) -> CallToolResult:
    """Format an error response with the MCP ``isError`` flag."""
    return CallToolResult(
        content=[types.TextContent(type="text", text=f"Error: {error}")],
        isError=True,
    )
