"""Duct's MCP server: the Streamable HTTP transport, stateless and JSON-only.

An outside agent (Claude Code, Codex, Cursor) POSTs one JSON-RPC message to
``/mcp`` and gets one JSON answer back. That is the whole transport this server
needs, and it is why there is no SDK here: with no sessions, no server-sent
events and no requests from server to client, MCP reduces to five methods,
and each one is a dictionary. The ``mcp`` SDK's server is built around a
session manager that has to run inside the app's lifespan; that machinery buys
streams this server never opens. OAuth (``#197``'s second phase) is the point
where its auth pieces would earn their keep.

Stateless means every request stands alone: the bearer token says who is
asking, and nothing is remembered between calls, so any replica can answer
any request. ``initialize`` still negotiates a version, because a client
refuses a server that does not echo one it speaks.

Spec: modelcontextprotocol.io/specification, revisions listed in
``PROTOCOL_VERSIONS``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from agents.core.tool_schema import tool_schema
from models.auth import McpToken, User

logger = logging.getLogger(__name__)

# Newest first. A client asking for one of these gets it back; one asking for
# anything else gets the newest, and decides for itself whether to continue.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

# JSON-RPC 2.0 error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Clients hand tool text to the model verbatim; a runaway answer costs the
# person's context window, not ours.
_TEXT_MAX_CHARS = 40_000


@dataclass
class Caller:
    """Who a tool runs for. Tools read ``user`` for every access decision and
    never take a user or owner from their arguments."""

    user: User
    token: McpToken
    session: Session


class ToolError(Exception):
    """A failure the calling model should read and can act on: a wrong id, a
    value out of range. Returned as a tool result with ``isError`` rather than
    a protocol error, so the model sees it and corrects the call."""


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    args: type[BaseModel]
    run: Callable[[BaseModel, Caller], dict[str, Any]]
    read_only: bool

    def descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": tool_schema(self.args),
            # Hints, not guarantees, in the spec's words; a client uses them to
            # decide what to confirm with the person before calling.
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }


def _result(id_: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    # The JSON as text too: the spec asks for it beside structuredContent, and
    # several clients still show the model only the text.
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > _TEXT_MAX_CHARS:
        text = text[:_TEXT_MAX_CHARS] + "…"
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": is_error,
    }


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        where = ".".join(str(p) for p in err["loc"]) or "arguments"
        parts.append(f"{where}: {err['msg']}")
    return "Invalid arguments. " + "; ".join(parts)


def _call_tool(tool: Tool, arguments: Any, caller: Caller) -> dict[str, Any]:
    try:
        args = tool.args.model_validate(arguments or {})
    except ValidationError as exc:
        return _tool_result({"error": _validation_message(exc)}, is_error=True)
    try:
        return _tool_result(tool.run(args, caller))
    except ToolError as exc:
        return _tool_result({"error": str(exc)}, is_error=True)


def negotiate(requested: Any) -> str:
    return requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]


def handle(
    message: Any,
    caller: Caller,
    tools: dict[str, Tool],
    *,
    instructions: str,
    version: str,
) -> dict[str, Any] | None:
    """Answer one JSON-RPC message. ``None`` for a notification, which the
    transport acknowledges with an empty 202."""
    if isinstance(message, list):
        # Batching was in 2025-03-26 and removed in 2025-06-18; no client this
        # server is for sends one.
        return error(None, INVALID_REQUEST, "Batched requests are not supported.")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return error(None, INVALID_REQUEST, "Expected a JSON-RPC 2.0 message.")
    method = message.get("method")
    if "id" not in message:
        # notifications/initialized, cancellations: nothing to answer.
        return None
    id_ = message["id"]
    if not isinstance(method, str):
        return error(id_, INVALID_REQUEST, "Missing method.")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return error(id_, INVALID_PARAMS, "params must be an object.")

    if method == "initialize":
        return _result(id_, {
            "protocolVersion": negotiate(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "duct", "title": "Duct", "version": version},
            "instructions": instructions,
        })
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": [tool.descriptor() for tool in tools.values()]})
    if method == "tools/call":
        tool = tools.get(params.get("name"))
        if tool is None:
            return error(id_, INVALID_PARAMS, f"Unknown tool: {params.get('name')!r}")
        return _result(id_, _call_tool(tool, params.get("arguments"), caller))
    return error(id_, METHOD_NOT_FOUND, f"Method not found: {method}")
