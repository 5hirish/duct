"""Talking to a connected server: open a session, list its tools, call one.

Each operation opens its own session (``initialize``, the request, close).
That is one extra round trip per call, and it buys statelessness: no session
outlives the request that needed it, so a redeploy, a parked run or a server
that forgets sessions costs nothing. A server's tool list is cached by the
caller for the life of an agent run (``agents/core/mcp_tools.py``), which is
where repeated round trips would actually add up.

Failures come back as ``McpCallError`` with a code the agent can act on:
``reauth_required`` (signed out, nothing works until the user reconnects),
``unreachable`` and ``protocol_error``. The SDK reports an HTTP failure from
inside its task group, so the cause arrives wrapped in exception groups;
``_classify`` digs it out.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession
from mcp import types as mt
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

from service.crawl.fetcher import SSRFError
from service.mcp import http as mcp_http
from service.mcp import oauth
from service.mcp.oauth import AUTH_KEY, AUTH_OAUTH, OAuthFailed
from service.mcp.store import API_KEY, NEEDS_REAUTH, RESOURCE, TOKEN_ENDPOINT, ServerAccess, with_tokens

logger = logging.getLogger(__name__)

CLIENT_INFO = mt.Implementation(name=oauth.CLIENT_NAME, version=oauth.CLIENT_VERSION)
# A server with more pages of tools than this is listing something other
# than tools; stop rather than page forever.
MAX_TOOL_PAGES = 10

CODE_REAUTH = "reauth_required"
CODE_UNREACHABLE = "unreachable"
CODE_PROTOCOL = "protocol_error"

# Persist credentials a refresh changed (or the reauth flag a refused refresh
# set). The caller decides how: a thread with a DB session, in practice.
CredentialSink = Callable[[dict], Awaitable[None]]


class McpCallError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str = ""
    title: str = ""
    input_schema: dict = field(default_factory=dict)
    # Only what the server itself declares. A tool that says nothing is not
    # assumed harmless: unannotated means "ask first".
    read_only: bool = False


@dataclass(frozen=True)
class ToolResult:
    is_error: bool
    text: str
    structured: Any = None


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


async def _refresh(access: ServerAccess, sink: CredentialSink | None) -> str:
    tokens = access.tokens()
    if not tokens.refresh_token:
        raise McpCallError(CODE_REAUTH, f"{access.name} needs signing in again.")
    try:
        fresh = await oauth.refresh(
            token_endpoint=str(access.credentials.get(TOKEN_ENDPOINT) or ""),
            registration=access.registration(),
            refresh_token=tokens.refresh_token,
            resource=str(access.credentials.get(RESOURCE) or access.url),
        )
    except OAuthFailed as exc:
        if sink is not None:
            await sink({**access.credentials, NEEDS_REAUTH: True})
        raise McpCallError(CODE_REAUTH, f"{access.name} needs signing in again.") from exc
    updated = with_tokens(access.credentials, fresh)
    if sink is not None:
        await sink(updated)
    # In place, so the next call this run makes starts from the fresh token
    # rather than refreshing again from the one the server just retired.
    access.credentials.clear()
    access.credentials.update(updated)
    return fresh.access_token


async def _bearer(access: ServerAccess, sink: CredentialSink | None) -> str | None:
    if access.auth == AUTH_KEY:
        return str(access.credentials.get(API_KEY) or "") or None
    if access.auth != AUTH_OAUTH:
        return None
    if access.credentials.get(NEEDS_REAUTH):
        raise McpCallError(CODE_REAUTH, f"{access.name} needs signing in again.")
    tokens = access.tokens()
    if tokens.expiring() and tokens.refresh_token:
        return await _refresh(access, sink)
    return tokens.access_token or None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def _leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        out: list[BaseException] = []
        for inner in exc.exceptions:
            out += _leaves(inner)
        return out
    chain = [exc]
    if exc.__cause__ is not None:
        chain += _leaves(exc.__cause__)
    return chain


def _classify(exc: BaseException, name: str) -> McpCallError:
    leaves = _leaves(exc)
    for leaf in leaves:
        if isinstance(leaf, McpCallError):
            return leaf
        if isinstance(leaf, httpx.HTTPStatusError) and leaf.response.status_code in (401, 403):
            return McpCallError(CODE_REAUTH, f"{name} refused Duct's credentials; it needs signing in again.")
    for leaf in leaves:
        if isinstance(leaf, SSRFError):
            return McpCallError(CODE_UNREACHABLE, f"{name} is not on the public internet.")
        if isinstance(leaf, httpx.TimeoutException):
            return McpCallError(CODE_UNREACHABLE, f"{name} did not answer in time.")
        if isinstance(leaf, httpx.HTTPStatusError):
            return McpCallError(CODE_UNREACHABLE, f"{name} answered HTTP {leaf.response.status_code}.")
        if isinstance(leaf, httpx.HTTPError):
            return McpCallError(CODE_UNREACHABLE, f"{name} could not be reached ({type(leaf).__name__}).")
        if isinstance(leaf, McpError):
            return McpCallError(CODE_PROTOCOL, f"{name} returned an error: {leaf.error.message}")
    logger.warning("mcp: unclassified failure talking to %s", name, exc_info=exc)
    return McpCallError(CODE_PROTOCOL, f"Talking to {name} failed ({type(exc).__name__}).")


@asynccontextmanager
async def _session(url: str, token: str | None) -> AsyncIterator[ClientSession]:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with mcp_http.guarded_client(headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _session_id):
            async with ClientSession(
                read,
                write,
                read_timeout_seconds=timedelta(seconds=mcp_http.READ_TIMEOUT_SECONDS),
                client_info=CLIENT_INFO,
            ) as session:
                await session.initialize()
                yield session


async def _with_session(
    access: ServerAccess,
    sink: CredentialSink | None,
    work: Callable[[ClientSession], Awaitable[Any]],
) -> Any:
    """Run ``work`` in a fresh session, refreshing once on a 401."""
    token = await _bearer(access, sink)
    try:
        async with _session(access.url, token) as session:
            return await work(session)
    except Exception as exc:  # noqa: BLE001 — every failure becomes a code
        failure = _classify(exc, access.name)
    if failure.code != CODE_REAUTH or access.auth != AUTH_OAUTH or not access.tokens().refresh_token:
        raise failure
    # The server said no to a token we thought was live: revoked early, or a
    # clock that disagrees with ours. One refresh, one retry, then it is real.
    token = await _refresh(access, sink)
    try:
        async with _session(access.url, token) as session:
            return await work(session)
    except Exception as exc:  # noqa: BLE001
        raise _classify(exc, access.name) from exc


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def _tool_info(tool: mt.Tool) -> ToolInfo:
    annotations = tool.annotations
    return ToolInfo(
        name=tool.name,
        title=(tool.title or (annotations.title if annotations else None) or ""),
        description=tool.description or "",
        input_schema=dict(tool.inputSchema or {}),
        read_only=bool(annotations and annotations.readOnlyHint is True),
    )


async def list_tools(access: ServerAccess, sink: CredentialSink | None = None) -> list[ToolInfo]:
    async def work(session: ClientSession) -> list[ToolInfo]:
        tools: list[ToolInfo] = []
        cursor: str | None = None
        for _ in range(MAX_TOOL_PAGES):
            page = await session.list_tools(cursor=cursor) if cursor else await session.list_tools()
            tools += [_tool_info(t) for t in page.tools]
            cursor = page.nextCursor
            if not cursor:
                break
        return tools

    return await _with_session(access, sink, work)


def _text_of(block: Any) -> str:
    if isinstance(block, mt.TextContent):
        return block.text
    if isinstance(block, mt.ImageContent):
        return "[an image the server returned; not shown]"
    if isinstance(block, mt.AudioContent):
        return "[audio the server returned; not shown]"
    if isinstance(block, mt.ResourceLink):
        return f"[resource: {block.name} {block.uri}]"
    if isinstance(block, mt.EmbeddedResource):
        resource = block.resource
        return getattr(resource, "text", None) or f"[resource: {resource.uri}]"
    return ""


async def call_tool(
    access: ServerAccess,
    name: str,
    arguments: dict[str, Any],
    sink: CredentialSink | None = None,
) -> ToolResult:
    async def work(session: ClientSession) -> ToolResult:
        result = await session.call_tool(name, arguments or {})
        text = "\n\n".join(t for t in (_text_of(b) for b in result.content) if t)
        return ToolResult(is_error=bool(result.isError), text=text, structured=result.structuredContent)

    return await _with_session(access, sink, work)


async def probe(access: ServerAccess) -> int:
    """How many tools the server offers, proving the credentials work."""
    return len(await list_tools(access))
