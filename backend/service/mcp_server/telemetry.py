"""What Duct's MCP server reports about itself: which tools agents call, how
long each takes, how each fails, and which agent was calling.

The events are PostHog's MCP Analytics schema (``$mcp_tool_call``,
``$mcp_initialize``), sent through ``service/analytics.capture_mcp``, so the
dashboards PostHog already draws for an MCP server work without a query
written here. Nothing in this file names the vendor.

Three rules, each held by ``tests/test_mcp_telemetry.py``:

* **Arguments and results never leave.** A tool's arguments are a project's
  pitch, personas and competitors, and its result is the same again; the
  schema's ``$mcp_parameters`` and ``$mcp_response`` are left out, as the
  backend's AI callback leaves out prompts (``privacy_mode``). What is sent
  is the tool, the timing, the size, the error class and the model's own
  one-line reason, redacted.
* **Reporting never changes a reply.** Every capture runs after the reply is
  built, inside a ``try`` that swallows everything: a broken analytics client
  is a missing event, never a failed tool call.
* **A session is a label.** ``initialize`` mints an ``Mcp-Session-Id`` and the
  client echoes it; it is hashed before it is sent and never looked up, so
  the server stays stateless. A client that sends none gets a fresh label per
  request, which is what PostHog's spec asks for rather than grouping calls
  that may belong to different conversations.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from service import analytics
from service.mcp_server.protocol import Caller

logger = logging.getLogger(__name__)

SESSION_HEADER = "Mcp-Session-Id"
SERVER_NAME = "duct"
_TEXT_MAX = 2048

# Free text the calling model wrote (its reason for a call) or a message that
# may quote a value. Each is replaced, then the whole is cut.
_REDACTIONS = (
    (re.compile(r"\bduct_mcp_[A-Za-z0-9_-]+"), "[redacted]"),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "[redacted]"),
    (re.compile(r"\bph[a-z]_[A-Za-z0-9_-]{20,}"), "[redacted]"),
    (re.compile(r"\bBearer\s+\S+", re.IGNORECASE), "Bearer [redacted]"),
    (re.compile(r"(?i)\b(token|secret|password|api[_-]?key)\s*[:=]\s*\S+"), r"\1=[redacted]"),
    (re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "://[redacted]@"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    # A ten-digit phone in its usual spellings, and not a date or an id.
    (re.compile(r"(?<![\w-])\+?(?:\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?![\w-])"), "[number]"),
)


def redact(text: str | None) -> str | None:
    if not text:
        return None
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text[:_TEXT_MAX]


@dataclass(frozen=True)
class Transport:
    """What the HTTP request says about the client, beside the JSON-RPC body."""

    session_id: str | None = None
    user_agent: str | None = None
    vendor_client: str | None = None
    protocol_version: str | None = None


def new_session_id() -> str:
    return uuid.uuid4().hex


def _session_label(session_id: str | None) -> str:
    if not session_id:
        return f"ses_{uuid.uuid4().hex}"
    return "ses_" + hashlib.sha256(session_id.encode()).hexdigest()[:32]


def _token_kind(caller: Caller) -> str:
    # A signed-in agent's row carries the client id it registered under; a
    # pasted token carries none.
    return "agent" if caller.token.client_id else "token"


def _client_info(params: dict[str, Any]) -> dict[str, Any]:
    info = params.get("clientInfo")
    if not isinstance(info, dict):
        meta = params.get("_meta")
        info = meta.get("io.modelcontextprotocol/clientInfo") if isinstance(meta, dict) else None
    if not isinstance(info, dict):
        return {}
    return {"client_name": info.get("name"), "client_version": info.get("version")}


def _registered_client_name(caller: Caller) -> str | None:
    """The name a signed-in agent registered with, the fallback when a tool
    call carries no clientInfo. A stateless server sees clientInfo only on
    ``initialize``, so without this most calls would have no client at all."""
    if not caller.token.client_id:
        return None
    from service.mcp_server import oauth

    registered = oauth.client(caller.token.client_id)
    return registered.name if registered else None


def observe(
    message: Any,
    caller: Caller,
    transport: Transport,
    *,
    started_at: datetime,
    duration_ms: float,
    failure: BaseException | None,
    version: str,
) -> None:
    """Report one answered message. Never raises."""
    try:
        _observe(message, caller, transport, started_at, duration_ms, failure, version)
    except Exception:  # noqa: BLE001 — reporting a call must never become its failure
        logger.debug("mcp: telemetry dropped", exc_info=True)


def _observe(message, caller, transport, started_at, duration_ms, failure, version) -> None:
    if not isinstance(message, dict):
        return
    method = message.get("method")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    common = {
        "server_name": SERVER_NAME,
        "server_version": version,
        "protocol_version": transport.protocol_version,
        "client_user_agent": transport.user_agent,
        "vendor_client": transport.vendor_client,
        "token_kind": _token_kind(caller),
        **_client_info(params),
    }
    if not common.get("client_name"):
        common["client_name"] = _registered_client_name(caller)
    distinct_id = str(caller.user.id)
    session = _session_label(transport.session_id)

    if method == "initialize":
        analytics.capture_mcp(
            "initialize",
            distinct_id=distinct_id,
            session_id=session,
            started_at=started_at,
            properties={**common, "protocol_version": params.get("protocolVersion") or transport.protocol_version},
        )
        return

    outcome = caller.outcome
    # Only tools this server has: an unknown name never reached _call_tool,
    # and PostHog's spec keeps those out of the tool-call counts.
    if method != "tools/call" or outcome is None:
        return
    if failure is not None:
        outcome.error_type = "internal"
        outcome.error_message = type(failure).__name__
    analytics.capture_mcp(
        "tool_call",
        distinct_id=distinct_id,
        session_id=session,
        started_at=started_at,
        properties={
            **common,
            "tool_name": outcome.tool,
            "resource_name": outcome.tool,
            "is_error": outcome.error_type is not None,
            "error_type": outcome.error_type,
            "error_message": redact(outcome.error_message),
            "duration_ms": round(duration_ms, 1),
            "intent": redact(outcome.intent),
            "intent_source": "context_parameter" if outcome.intent else None,
            "project_id": outcome.project_id,
            "result_chars": outcome.result_chars,
            "truncated": outcome.truncated,
            "toolset_version": version,
        },
    )


def refused(reason: str, transport: Transport, *, distinct_id: str | None = None) -> None:
    """A request turned away before any tool ran: a token that did not
    resolve, or one over its rate limit. A first call with no token at all is
    the sign-in discovery step every OAuth client makes, not a refusal, and
    is never reported. Never raises."""
    try:
        session = _session_label(transport.session_id)
        properties: dict[str, Any] = {
            "reason": reason,
            "server_name": SERVER_NAME,
            "client_user_agent": transport.user_agent,
            "vendor_client": transport.vendor_client,
        }
        if distinct_id is None:
            # Nobody to attribute it to: keep it off every person profile.
            properties["$process_person_profile"] = False
        analytics.capture_mcp(
            "mcp_request_refused",
            distinct_id=distinct_id or session,
            session_id=session,
            properties=properties,
        )
    except Exception:  # noqa: BLE001 — same rule as observe()
        logger.debug("mcp: telemetry dropped", exc_info=True)
