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
refuses a server that does not echo one it speaks. The ``Mcp-Session-Id`` it
hands out is a label, not a session: nothing is stored under it and nothing
is refused for lacking it. It exists so analytics can tell one agent
conversation from the next (``service/mcp_server/telemetry.py``).

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
from config import get_configs
from models.auth import McpToken, User
from service.mcp_server import scopes as mcp_scopes

logger = logging.getLogger(__name__)

# Where the server answers. The OAuth metadata names it as the protected
# resource, so the route and the metadata must not disagree.
MCP_PATH = "/mcp"

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

# An optional argument on every tool: the calling model says, in a sentence,
# why it is calling. It is the one signal that says what people wanted from
# an agent that Duct's tools could not yet do, so it decides what gets built
# next. Taken out before validation, so it never reaches a tool body and the
# `extra="forbid"` argument models stay strict about everything else.
CONTEXT_ARG = "context"
_CONTEXT_MAX_CHARS = 2048
_CONTEXT_SCHEMA = {
    "type": "string",
    "maxLength": _CONTEXT_MAX_CHARS,
    "description": (
        "Optional. In one sentence, why you are calling this tool. Describe the goal in "
        "general terms and refer to people by role (\"the founder\"), never by name or email."
    ),
}


@dataclass
class ToolOutcome:
    """What one tools/call came to, for telemetry. Written by ``_call_tool``
    and read by the route once the reply exists; no tool reads it."""

    tool: str
    intent: str | None = None
    # None on success. Otherwise a low-cardinality label: "validation" for
    # arguments the schema refused, a ToolError's code, or "internal" (set by
    # the route) for an exception nothing caught.
    error_type: str | None = None
    error_message: str | None = None
    project_id: str | None = None
    result_chars: int = 0
    truncated: bool = False


@dataclass
class Caller:
    """Who a tool runs for. Tools read ``user`` for every access decision and
    never take a user or owner from their arguments."""

    user: User
    token: McpToken
    session: Session
    outcome: ToolOutcome | None = None

    @property
    def scopes(self) -> frozenset[str]:
        return mcp_scopes.parse(self.token.scopes)

    @property
    def project_grant(self) -> frozenset[str] | None:
        """The projects this connection may reach, or None for all of the
        person's. Membership is still checked on every call: a grant never
        reaches a project the person has since lost."""
        ids = self.token.project_ids
        return None if ids is None else frozenset(str(i) for i in ids)

    def allows_project(self, project_id: Any) -> bool:
        grant = self.project_grant
        return grant is None or str(project_id) in grant


class ToolError(Exception):
    """A failure the calling model should read and can act on: a wrong id, a
    value out of range. Returned as a tool result with ``isError`` rather than
    a protocol error, so the model sees it and corrects the call.

    ``code`` is what telemetry counts, never the message: "not_found" and
    "rate_limited" are the two worth telling apart from a plain refusal."""

    def __init__(self, message: str, *, code: str = "refused") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    args: type[BaseModel]
    run: Callable[[BaseModel, Caller], dict[str, Any]]
    read_only: bool
    # Replaces what the person set (update_project). Clients read the hint to
    # confirm the call with the person first.
    destructive: bool = False
    # The capability a connection must have been granted (scopes.py).
    scope: str = mcp_scopes.PROJECTS
    # Reads text a stranger wrote (a crawled page, a search term, a caption).
    # Clients use the hint to treat the result as data, not instructions.
    open_world: bool = False

    def available_to(self, caller: "Caller") -> bool:
        """Granted, and not a write while writes are switched off. A tool
        that fails either is absent from the list, not offered and refused."""
        if self.scope not in caller.scopes:
            return False
        return self.read_only or get_configs().mcp_write_tools_enabled

    def descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": _with_context(tool_schema(self.args)),
            # Hints, not guarantees, in the spec's words; a client uses them to
            # decide what to confirm with the person before calling.
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "idempotentHint": True,
                "openWorldHint": self.open_world,
            },
        }


@dataclass(frozen=True)
class PromptArgument:
    name: str
    description: str
    required: bool = False


@dataclass(frozen=True)
class Prompt:
    """A playbook the person can run from their agent (a slash command in
    Claude Code and Gemini CLI). ``render`` returns the text of one user
    message; the same text is reachable as a tool for clients that list no
    prompts, so a prompt is a convenience and never the only way in."""

    name: str
    title: str
    description: str
    arguments: tuple[PromptArgument, ...]
    render: Callable[[dict[str, str], "Caller"], str]
    scope: str = mcp_scopes.REPORTS

    def descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "arguments": [
                {"name": a.name, "description": a.description, "required": a.required} for a in self.arguments
            ],
        }


def _get_prompt(id_: Any, prompt: Prompt, arguments: Any, caller: "Caller") -> dict[str, Any]:
    if prompt.scope not in caller.scopes:
        return error(id_, INVALID_PARAMS, f"{prompt.name} is not allowed on this connection.")
    args = {str(k): str(v) for k, v in (arguments or {}).items()} if isinstance(arguments, dict) else {}
    missing = [a.name for a in prompt.arguments if a.required and not args.get(a.name)]
    if missing:
        return error(id_, INVALID_PARAMS, f"Missing argument: {', '.join(missing)}")
    try:
        text = prompt.render(args, caller)
    except ToolError as exc:
        return error(id_, INVALID_PARAMS, str(exc))
    return _result(id_, {
        "description": prompt.description,
        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
    })


def _with_context(schema: dict[str, Any]) -> dict[str, Any]:
    properties = dict(schema.get("properties") or {})
    if CONTEXT_ARG in properties:
        return schema
    return {**schema, "type": "object", "properties": {**properties, CONTEXT_ARG: _CONTEXT_SCHEMA}}


def _split_context(arguments: Any) -> tuple[Any, str | None]:
    if not isinstance(arguments, dict) or CONTEXT_ARG not in arguments:
        return arguments, None
    rest = {k: v for k, v in arguments.items() if k != CONTEXT_ARG}
    intent = arguments[CONTEXT_ARG]
    # The schema says 2,048; a client need not honour it, and nothing after
    # this should handle more than that of a model's free text.
    intent = intent[:_CONTEXT_MAX_CHARS].strip() if isinstance(intent, str) else ""
    return rest, intent or None


def _result(id_: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _tool_result(payload: dict[str, Any], *, is_error: bool = False, outcome: ToolOutcome | None = None) -> dict[str, Any]:
    # The JSON as text too: the spec asks for it beside structuredContent, and
    # several clients still show the model only the text.
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if outcome is not None:
        outcome.result_chars = len(text)
        outcome.truncated = len(text) > _TEXT_MAX_CHARS
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
    arguments, intent = _split_context(arguments)
    # Set before anything can raise, so an exception that escapes still leaves
    # the route a record of which tool it came from.
    outcome = caller.outcome = ToolOutcome(tool=tool.name, intent=intent)
    if not tool.available_to(caller):
        # A client can still call a name it remembers from another
        # connection; the answer says how to get it, so the model can tell
        # the person rather than retry.
        message = (
            f"{tool.name} is not allowed on this connection. The person can allow it in Duct "
            "(Settings, Connect your AI agent) and reconnect."
        )
        outcome.error_type, outcome.error_message = "not_granted", message
        return _tool_result({"error": message}, is_error=True, outcome=outcome)
    try:
        args = tool.args.model_validate(arguments or {})
    except ValidationError as exc:
        message = _validation_message(exc)
        outcome.error_type, outcome.error_message = "validation", message
        return _tool_result({"error": message}, is_error=True, outcome=outcome)
    project_id = getattr(args, "project_id", None)
    outcome.project_id = str(project_id) if project_id else None
    try:
        payload = tool.run(args, caller)
    except ToolError as exc:
        outcome.error_type, outcome.error_message = exc.code, str(exc)
        return _tool_result({"error": str(exc)}, is_error=True, outcome=outcome)
    # A draft that created the project names it only in its result.
    outcome.project_id = outcome.project_id or (str(payload.get("project_id")) if payload.get("project_id") else None)
    return _tool_result(payload, outcome=outcome)


def negotiate(requested: Any) -> str:
    return requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]


def handle(
    message: Any,
    caller: Caller,
    tools: dict[str, Tool],
    *,
    instructions: str,
    version: str,
    prompts: dict[str, Prompt] | None = None,
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
            "capabilities": {
                "tools": {"listChanged": False},
                **({"prompts": {"listChanged": False}} if prompts else {}),
            },
            "serverInfo": {"name": "duct", "title": "Duct", "version": version},
            "instructions": instructions,
        })
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": [tool.descriptor() for tool in tools.values() if tool.available_to(caller)]})
    if method == "tools/call":
        tool = tools.get(params.get("name"))
        if tool is None:
            return error(id_, INVALID_PARAMS, f"Unknown tool: {params.get('name')!r}")
        return _result(id_, _call_tool(tool, params.get("arguments"), caller))
    if method == "prompts/list" and prompts is not None:
        listed = [p.descriptor() for p in prompts.values() if p.scope in caller.scopes]
        return _result(id_, {"prompts": listed})
    if method == "prompts/get" and prompts is not None:
        prompt = prompts.get(params.get("name"))
        if prompt is None:
            return error(id_, INVALID_PARAMS, f"Unknown prompt: {params.get('name')!r}")
        return _get_prompt(id_, prompt, params.get("arguments"), caller)
    return error(id_, METHOD_NOT_FOUND, f"Method not found: {method}")
