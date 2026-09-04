"""
Thin wrapper around the MCP stdio client for the Voyager travel-tools server.

Provides:
  - mcp_tool_schemas()   → list of OpenAI-format tool dicts to pass to the LLM
  - call_mcp_tool()      → execute a named tool and return a JSON string result
"""

import json
import os
import logging
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

logger = logging.getLogger("voyager.mcp_client")

_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "mcp-server", "server.py")
_SERVER_PYTHON = os.path.join(os.path.dirname(__file__), "..", "..", "mcp-server", ".venv", "bin", "python")


@asynccontextmanager
async def _mcp_session():
    # The MCP SDK only inherits an allowlist of "safe" env vars, so anything the
    # server needs (API keys) must be passed through explicitly.
    env = get_default_environment()
    for key in ("BRAVE_API_KEY",):
        value = os.getenv(key)
        if value:
            env[key] = value

    params = StdioServerParameters(
        command=os.path.abspath(_SERVER_PYTHON),
        args=[os.path.abspath(_SERVER_SCRIPT)],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def mcp_tool_schemas() -> list[dict]:
    """Return MCP server tools as OpenAI-compatible function schemas."""
    async with _mcp_session() as session:
        tools = await session.list_tools()

    schemas = []
    for t in tools.tools:
        schema = {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema if t.inputSchema else {"type": "object", "properties": {}},
            },
        }
        schemas.append(schema)
    return schemas


async def call_mcp_tool(name: str, args: dict) -> str:
    """Call a tool on the MCP server and return its result as a JSON string."""
    async with _mcp_session() as session:
        result = await session.call_tool(name, args)

    # MCP returns a list of content blocks; collapse to a single JSON string
    if result.isError:
        return json.dumps({"error": f"MCP tool error: {name}"})

    parts = [block.text for block in result.content if hasattr(block, "text")]
    combined = " ".join(parts)

    # If it's already valid JSON pass it through, otherwise wrap it
    try:
        json.loads(combined)
        return combined
    except json.JSONDecodeError:
        return json.dumps({"result": combined})
