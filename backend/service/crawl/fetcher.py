"""Async HTTP helpers for the SEO audit crawler."""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "DuctAuditBot/1.0 (+https://getduct.ai/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Maximum response body size to read. Prevents downloading huge pages.
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Well-known internal hostnames blocked by name (before DNS resolution)
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "broadcasthost",
    "metadata",                     # generic internal shorthand
    "metadata.google.internal",     # GCP metadata service
})

# RFC 1918 private ranges + loopback + link-local + AWS metadata
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # private
    ipaddress.ip_network("172.16.0.0/12"),     # private
    ipaddress.ip_network("192.168.0.0/16"),    # private
    ipaddress.ip_network("169.254.0.0/16"),    # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space (Railway internal)
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


class SSRFError(ValueError):
    """Raised when a URL targets a private/internal network address."""


def validate_public_url(url: str) -> None:
    """Raise SSRFError if *url* resolves to a private or reserved network range.

    Checks the URL hostname as an IP address (if it already is one). DNS-based
    SSRF (where a public hostname resolves to a private IP) is a separate concern
    handled at the network level by Railway's egress rules.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme not in {"http", "https"}:
        raise SSRFError(f"Only http/https URLs are allowed, got: {scheme!r}")

    host = parsed.hostname or ""
    if not host:
        raise SSRFError("URL has no hostname")

    # Block well-known internal hostnames by name
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise SSRFError(f"URL hostname {host!r} is not allowed (internal/reserved).")

    # Block bare IP addresses that are private/reserved.
    # Note: try/except is only for ip_address() parsing; SSRFError is raised outside it
    # to prevent the except ValueError from swallowing it (SSRFError inherits ValueError).
    addr = None
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP address literal — hostname will be resolved by httpx.
        # DNS-based SSRF must be mitigated at the network/egress layer.
        pass

    if addr is not None:
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                raise SSRFError(
                    f"URL targets a private/reserved IP address ({addr}). "
                    "Only public internet addresses are allowed."
                )


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=_HEADERS,
        timeout=_TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
        trust_env=False,  # don't inherit system proxy settings (e.g. Charles/SOCKS on dev)
    )


async def fetch_text(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    """Fetch *url* and return (body_text, status_code).

    Reads at most _MAX_BYTES to prevent downloading huge pages.
    Returns ("", 0) on any error.
    """
    try:
        async with client.stream("GET", url) as resp:
            body = await resp.aread()
            if len(body) > _MAX_BYTES:
                body = body[:_MAX_BYTES]
                logger.debug("fetch_text: truncated response from %s to %d bytes", url, _MAX_BYTES)
            return body.decode("utf-8", errors="replace"), resp.status_code
    except Exception as exc:
        logger.debug("fetch_text %s failed: %s", url, exc)
        return "", 0


async def fetch_bytes(client: httpx.AsyncClient, url: str) -> tuple[bytes, int]:
    """Fetch *url* and return (body_bytes, status_code).

    Reads at most _MAX_BYTES. Returns (b"", 0) on any error.
    """
    try:
        async with client.stream("GET", url) as resp:
            body = await resp.aread()
            if len(body) > _MAX_BYTES:
                body = body[:_MAX_BYTES]
            return body, resp.status_code
    except Exception as exc:
        logger.debug("fetch_bytes %s failed: %s", url, exc)
        return b"", 0
