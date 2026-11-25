"""POST /mcp — Duct's MCP server, for agents outside Duct.

Not under ``/api`` and not behind ``validate_api_key``: an agent is not the
Duct app and carries no ``X-API-Key``. Its one credential is an MCP token
(``service/mcp_tokens.py``), pasted or minted by browser sign-in
(``routes/mcp_oauth.py``), resolved by ``get_mcp_caller``, and accepted here
and nowhere else. A sign-in JWT sent here is refused the same way a mistyped
token is.

No Origin check, though the transport spec asks local servers for one: it
guards against a web page reaching a server on the visitor's own machine, and
here every request must also carry a bearer token no web page has.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from sqlmodel import Session
from starlette.status import (
    HTTP_202_ACCEPTED,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_405_METHOD_NOT_ALLOWED,
    HTTP_413_CONTENT_TOO_LARGE,
)

from db.session import get_session
from service.analytics import identify_user
from service.mcp_server.protocol import (
    INTERNAL_ERROR,
    PARSE_ERROR,
    MCP_PATH,
    PROTOCOL_VERSIONS,
    Caller,
    error,
    handle,
)
from service.mcp_server import oauth, telemetry
from service.mcp_server.prompts import PROMPTS
from service.mcp_server.tools import INSTRUCTIONS, TOOLS, TOOLSET_VERSION
from service.mcp_tokens import resolve
from service.ratelimit import RateLimit
from utils.dates import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])

# Twice the largest draft the project routes accept (128 KB): room for the
# JSON-RPC envelope, and a bound on what one request makes us parse.
_MAX_BODY_BYTES = 256_000

# Per token. An agent working through a project makes a handful of calls; a
# loop makes thousands, and the cost of each lands on the database.
_CALL_LIMIT = RateLimit(limit=120, window_seconds=60.0)

def _challenge(*, presented: bool, host: str | None = None) -> dict[str, str]:
    """RFC 6750 §3, plus the RFC 9728 pointer that lets a client holding only
    this address find where to sign in. ``error`` only when a credential was
    sent: a first call carries none, and nothing about it was invalid."""
    params = ['realm="duct"']
    if presented:
        params.append('error="invalid_token"')
    if oauth.available():
        params += [f'resource_metadata="{oauth.resource_metadata_url(host)}"', f'scope="{oauth.SCOPE}"']
    return {"WWW-Authenticate": "Bearer " + ", ".join(params)}


def _transport(request: Request) -> telemetry.Transport:
    headers = request.headers
    return telemetry.Transport(
        session_id=headers.get(telemetry.SESSION_HEADER),
        user_agent=headers.get("user-agent"),
        vendor_client=headers.get("x-anthropic-client"),
        protocol_version=headers.get("mcp-protocol-version"),
    )


def get_mcp_caller(
    request: Request,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Caller:
    scheme, _, raw = (authorization or "").partition(" ")
    resolved = resolve(raw.strip(), session) if scheme.lower() == "bearer" and raw.strip() else None
    if resolved is None:
        # A call with no credential is how every OAuth client discovers the
        # sign-in, so only a credential that failed is worth counting: an
        # expired or revoked connection is a person whose agent stopped.
        if authorization:
            telemetry.refused("invalid_token", _transport(request))
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Sign in to Duct from your agent, or send a Duct MCP token as "
            "'Authorization: Bearer duct_mcp_…' (Settings, Connect your AI agent).",
            headers=_challenge(presented=bool(authorization), host=request.headers.get("host")),
        )
    token, user = resolved
    identify_user(user)
    try:
        _CALL_LIMIT.enforce(str(token.id), "Too many MCP requests. Slow down and try again shortly.")
    except HTTPException:
        telemetry.refused("rate_limited", _transport(request), distinct_id=str(user.id))
        raise
    return Caller(user=user, token=token, session=session)


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=HTTP_413_CONTENT_TOO_LARGE, detail="Request too large.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=HTTP_413_CONTENT_TOO_LARGE, detail="Request too large.")
    return bytes(body)


def _dispatch(message: Any, caller: Caller, transport: telemetry.Transport) -> dict[str, Any] | None:
    started_at, started = utcnow(), time.monotonic()
    failure: BaseException | None = None
    try:
        reply = handle(
            message, caller, TOOLS, instructions=INSTRUCTIONS, version=TOOLSET_VERSION, prompts=PROMPTS
        )
    except Exception as exc:  # noqa: BLE001 — one failed call is an error reply, never a dropped connection
        failure = exc
        # The tool's name in the line, because this record is also the error
        # report (service/analytics._LoggedExceptionHandler).
        logger.exception("mcp: %s failed", caller.outcome.tool if caller.outcome else _method(message))
        caller.session.rollback()
        id_ = message.get("id") if isinstance(message, dict) else None
        reply = error(id_, INTERNAL_ERROR, "Duct could not complete that request.")
    telemetry.observe(
        message,
        caller,
        transport,
        started_at=started_at,
        duration_ms=(time.monotonic() - started) * 1000,
        failure=failure,
        version=TOOLSET_VERSION,
    )
    return reply


def _method(message: Any) -> str:
    return str(message.get("method")) if isinstance(message, dict) else "request"


@router.post(MCP_PATH)
async def mcp_post(
    request: Request,
    caller: Caller = Depends(get_mcp_caller),
    mcp_protocol_version: str | None = Header(default=None),
) -> Response:
    # Sent on every request after initialize. An unknown one is a 400 by the
    # spec, so a client never proceeds believing we speak a version we don't.
    if mcp_protocol_version and mcp_protocol_version not in PROTOCOL_VERSIONS:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MCP-Protocol-Version. Supported: {', '.join(PROTOCOL_VERSIONS)}",
        )
    try:
        message = json.loads(await _read_body(request))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse(error(None, PARSE_ERROR, "Body is not valid JSON."), status_code=HTTP_400_BAD_REQUEST)
    transport = _transport(request)
    headers: dict[str, str] = {}
    if isinstance(message, dict) and message.get("method") == "initialize":
        # A label for analytics, minted here and echoed by the client on every
        # later request; never stored and never checked (protocol.py).
        session_id = telemetry.new_session_id()
        transport = replace(transport, session_id=session_id)
        headers[telemetry.SESSION_HEADER] = session_id
    reply = await run_in_threadpool(_dispatch, message, caller, transport)
    if reply is None:
        return Response(status_code=HTTP_202_ACCEPTED)
    return JSONResponse(reply, headers=headers)


@router.api_route(MCP_PATH, methods=["GET", "DELETE"], include_in_schema=False)
async def mcp_no_stream() -> Response:
    # GET would open a server-to-client event stream and DELETE would end a
    # session; a stateless server has neither, and 405 is how the spec says so.
    return Response(status_code=HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST"})
