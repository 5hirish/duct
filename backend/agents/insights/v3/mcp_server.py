"""Stdio MCP server that exposes pre-credentialed fetch functions as MCP tools.

Usage (programmatic, from runner.py):
    from agents.insights.v3.mcp_server import register, get_server

    register("fetch_search_terms", my_fn)
    server = get_server()

The runner writes a small bootstrap script to a temp file that imports and
runs this module after populating the registry via a JSON-serialised config
written to a temp file. See runner.py for the orchestration.

Registry model: each tool is a plain Python callable that accepts keyword args.
The connector type determines the required params (Google Ads / GA4 / GSC).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Callable
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level tool registry
# ---------------------------------------------------------------------------

_registry: dict[str, Callable[..., Any]] = {}
_descriptions: dict[str, str] = {}
_schemas: dict[str, dict[str, Any]] = {}

_GOOGLE_ADS_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_id": {
            "type": "string",
            "description": "Google Ads customer ID (digits only, no dashes)",
        },
        "date_from": {
            "type": "string",
            "description": "Start date in YYYY-MM-DD format",
        },
        "date_to": {
            "type": "string",
            "description": "End date in YYYY-MM-DD format",
        },
    },
    "required": ["customer_id", "date_from", "date_to"],
}

_GA4_SCHEMA = {
    "type": "object",
    "properties": {
        "property_id": {
            "type": "string",
            "description": "GA4 property ID (digits only, e.g. '123456789')",
        },
        "date_from": {
            "type": "string",
            "description": "Start date in YYYY-MM-DD format",
        },
        "date_to": {
            "type": "string",
            "description": "End date in YYYY-MM-DD format",
        },
    },
    "required": ["property_id", "date_from", "date_to"],
}

_GSC_SCHEMA = {
    "type": "object",
    "properties": {
        "site_url": {
            "type": "string",
            "description": "Search Console site URL (e.g. 'https://example.com')",
        },
        "date_from": {
            "type": "string",
            "description": "Start date in YYYY-MM-DD format",
        },
        "date_to": {
            "type": "string",
            "description": "End date in YYYY-MM-DD format",
        },
    },
    "required": ["site_url", "date_from", "date_to"],
}

_CONNECTOR_SCHEMAS = {
    "ga4": _GA4_SCHEMA,
    "gsc": _GSC_SCHEMA,
}


def _infer_schema(connector: str) -> dict[str, Any]:
    return _CONNECTOR_SCHEMAS.get(connector, _GOOGLE_ADS_SCHEMA)


def register(
    name: str,
    fn: Callable[..., Any],
    description: str = "",
    connector: str = "google_ads",
) -> None:
    """Register a fetch function as an MCP tool."""
    _registry[name] = fn
    _descriptions[name] = description or f"Fetch {name.replace('_', ' ')} data."
    _schemas[name] = _infer_schema(connector)


def clear() -> None:
    """Clear all registered tools (for test isolation)."""
    _registry.clear()
    _descriptions.clear()
    _schemas.clear()


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def get_server() -> Server:
    """Build and return a configured MCP Server instance."""
    server = Server("duct-fetch-tools")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=name,
                description=_descriptions[name],
                inputSchema=_schemas[name],
            )
            for name in _registry
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        fn = _registry.get(name)
        if fn is None:
            raise ValueError(f"Unknown tool: {name}")

        try:
            if inspect.iscoroutinefunction(fn):
                result = await fn(**arguments)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: fn(**arguments))
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            raise RuntimeError(f"Tool {name} failed: {exc}") from exc

        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return server


async def _run_stdio() -> None:
    server = get_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_run_stdio())
