"""POST /mcp — Duct's MCP server, for agents outside Duct.

Not under ``/api`` and not behind ``validate_api_key``: an agent is not the
Duct app and carries no ``X-API-Key``. Its one credential is a personal MCP
token (``service/mcp_tokens.py``), resolved by ``get_mcp_caller``, and that
token is accepted here and nowhere else. A sign-in JWT sent here is refused
the same way a mistyped token is.

No Origin check, though the transport spec asks local servers for one: it
guards against a web page reaching a server on the visitor's own machine, and
here every request must also carry a bearer token no web page has.
"""

from __future__ import annotations

import json
import logging
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
    PROTOCOL_VERSIONS,
    Caller,
    error,
    handle,
)
from service.mcp_server.tools import INSTRUCTIONS, TOOLS, TOOLSET_VERSION
from service.mcp_tokens import resolve
from service.ratelimit import RateLimit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])

MCP_PATH = "/mcp"

# Twice the largest draft the project routes accept (128 KB): room for the
# JSON-RPC envelope, and a bound on what one request makes us parse.
_MAX_BODY_BYTES = 256_000

# Per token. An agent working through a project makes a handful of calls; a
# loop makes thousands, and the cost of each lands on the database.
_CALL_LIMIT = RateLimit(limit=120, window_seconds=60.0)

_BEARER_CHALLENGE = {"WWW-Authenticate": 'Bearer realm="duct", error="invalid_token"'}


def get_mcp_caller(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Caller:
    scheme, _, raw = (authorization or "").partition(" ")
    resolved = resolve(raw.strip(), session) if scheme.lower() == "bearer" and raw.strip() else None
    if resolved is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Send a Duct MCP token as 'Authorization: Bearer duct_mcp_…'. "
            "Create one in Duct under Connect your AI agent.",
            headers=_BEARER_CHALLENGE,
        )
    token, user = resolved
    identify_user(user)
    _CALL_LIMIT.enforce(str(token.id), "Too many MCP requests. Slow down and try again shortly.")
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


def _dispatch(message: Any, caller: Caller) -> dict[str, Any] | None:
    try:
        return handle(message, caller, TOOLS, instructions=INSTRUCTIONS, version=TOOLSET_VERSION)
    except Exception:  # noqa: BLE001 — one failed call is an error reply, never a dropped connection
        logger.exception("mcp: request failed")
        caller.session.rollback()
        id_ = message.get("id") if isinstance(message, dict) else None
        return error(id_, INTERNAL_ERROR, "Duct could not complete that request.")


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
    reply = await run_in_threadpool(_dispatch, message, caller)
    if reply is None:
        return Response(status_code=HTTP_202_ACCEPTED)
    return JSONResponse(reply)


@router.api_route(MCP_PATH, methods=["GET", "DELETE"], include_in_schema=False)
async def mcp_no_stream() -> Response:
    # GET would open a server-to-client event stream and DELETE would end a
    # session; a stateless server has neither, and 405 is how the spec says so.
    return Response(status_code=HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST"})
