"""Async HTTP helpers for the SEO audit crawler.

Fetches pages using the Googlebot mobile user-agent so signals reflect
what Google actually receives rather than a generic bot identity.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Googlebot mobile UA (mobile-first indexing default since 2019).
# Source: https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers
_GOOGLEBOT_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

_HEADERS = {
    "User-Agent": _GOOGLEBOT_MOBILE_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Maximum response body size to read. Prevents downloading huge pages.
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Response headers we care about for SEO signals.
_CAPTURE_HEADERS = frozenset({
    "x-robots-tag",
    "vary",
    "cache-control",
    "last-modified",
    "link",
    "content-type",
})

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


@dataclass
class FetchResult:
    """Rich result from a single HTTP fetch."""
    text: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    redirect_chain: list[dict] = field(default_factory=list)  # [{"url": ..., "status": ...}]
    ttfb_ms: float = 0.0


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
    addr = None
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
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
        trust_env=False,
    )


def _extract_headers(resp: httpx.Response) -> dict[str, str]:
    """Extract the subset of response headers relevant for SEO signals."""
    return {
        k.lower(): v
        for k, v in resp.headers.items()
        if k.lower() in _CAPTURE_HEADERS
    }


def _build_redirect_chain(resp: httpx.Response) -> list[dict]:
    """Build a list of redirect hops from httpx history."""
    chain = []
    for r in resp.history:
        chain.append({"url": str(r.url), "status": r.status_code})
    return chain


async def fetch(client: httpx.AsyncClient, url: str) -> FetchResult:
    """Fetch *url* and return a rich FetchResult.

    Captures response headers, redirect chain, and TTFB in addition to
    body text and status code.  Returns an empty FetchResult on any error.
    """
    try:
        t0 = time.monotonic()
        async with client.stream("GET", url) as resp:
            ttfb_ms = (time.monotonic() - t0) * 1000
            body = await resp.aread()
            if len(body) > _MAX_BYTES:
                body = body[:_MAX_BYTES]
                logger.debug("fetch: truncated response from %s to %d bytes", url, _MAX_BYTES)
            return FetchResult(
                text=body.decode("utf-8", errors="replace"),
                status=resp.status_code,
                headers=_extract_headers(resp),
                redirect_chain=_build_redirect_chain(resp),
                ttfb_ms=round(ttfb_ms, 1),
            )
    except Exception as exc:
        logger.debug("fetch %s failed: %s", url, exc)
        return FetchResult(text="", status=0)


async def fetch_text(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    """Fetch *url* and return (body_text, status_code).

    Lightweight wrapper around fetch() for callers that only need text + status.
    """
    result = await fetch(client, url)
    return result.text, result.status


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
