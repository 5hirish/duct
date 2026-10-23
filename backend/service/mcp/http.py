"""HTTP for MCP servers: every request to a public https address.

A server URL is whatever a user typed, and the authorization server, token
endpoint and registration endpoint are whatever that server's metadata says, so
each request here is one somebody else aims. One client factory serves all of
them, with the crawl fetcher's resolved-address check on every request and
every redirect hop (``service/crawl/fetcher.assert_public_url``), plus https
only: a token has no business crossing the network in clear.

Callers reach the factory as ``mcp_http.guarded_client`` rather than importing
the name, so a test can swap the transport underneath every caller at once.

httpx2, not the httpx the rest of the backend uses: the SDK's transport
accepts only its own client, and discovery and token requests share this one
factory so the guard exists once. It comes with ``mcp``.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

import httpx2

from service.crawl.fetcher import SSRFError, assert_public_url, validate_public_url

logger = logging.getLogger(__name__)

# A tool call can run for a while (a keyword research job, a crawl), and a
# streamed result is silent between events, so reads get room that connects
# do not.
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 120.0
TIMEOUT = httpx2.Timeout(30.0, connect=CONNECT_TIMEOUT_SECONDS, read=READ_TIMEOUT_SECONDS)
MAX_REDIRECTS = 5


class UnsafeServerUrl(ValueError):
    """A server address Duct will not call. The message is safe to show."""


def canonical_url(raw: str) -> str:
    """The address a server is stored and called under, or ``UnsafeServerUrl``.

    https only, no credentials in the URL, not an internal address by name or
    literal (the resolved address is checked again on every request). The host
    is lowercased and the fragment dropped so one server is one row; the path
    is kept exactly, because servers disagree about a trailing slash.
    """
    url = (raw or "").strip()
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeServerUrl("That is not a valid address.") from exc
    if parts.scheme != "https":
        raise UnsafeServerUrl("An MCP server address starts with https://.")
    if not parts.hostname:
        raise UnsafeServerUrl("That address has no host.")
    if parts.username or parts.password:
        raise UnsafeServerUrl("Put the key in the key field, not in the address.")
    try:
        validate_public_url(url)
    except SSRFError as exc:
        raise UnsafeServerUrl("Duct only connects to servers on the public internet.") from exc
    host = parts.hostname.lower()
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return urlunsplit(("https", netloc, parts.path, parts.query, ""))


async def _guard(request: httpx2.Request) -> None:
    if request.url.scheme != "https":
        raise SSRFError(f"MCP requests are https only, not {request.url.scheme}")
    try:
        await assert_public_url(str(request.url))
    except SSRFError:
        logger.warning("mcp: refused request to non-public address %s", request.url.host)
        raise


def guarded_client(*, headers: dict[str, str] | None = None) -> httpx2.AsyncClient:
    """An async client for one server conversation. The caller closes it.

    ``trust_env=False`` so an ambient proxy setting cannot route a user's
    token somewhere nobody chose. httpx2 drops ``Authorization`` itself when a
    redirect changes origin.
    """
    return httpx2.AsyncClient(
        headers=headers or {},
        timeout=TIMEOUT,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        trust_env=False,
        event_hooks={"request": [_guard]},
    )
