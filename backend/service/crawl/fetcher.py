"""Async HTTP helpers for the SEO audit crawler.

Fetches pages using the Googlebot mobile user-agent so signals reflect
what Google actually receives rather than a generic bot identity.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
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
    "Accept-Encoding": "gzip, deflate",
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


class SiteUnreachableError(RuntimeError):
    """The audited URL produced no HTTP response at all.

    Distinct from a 4xx/5xx, which is an observation worth auditing ("your site
    blocks Googlebot"). No response means there is nothing to audit, and a
    report built on it is fiction: the pipeline stops here instead.
    """

    def __init__(self, url: str) -> None:
        super().__init__(
            f"Could not reach {url}: no HTTP response (DNS, TLS, a timeout or a "
            "network block). Check the address and try again."
        )
        self.url = url


def _blocked_reason(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Why *addr* is off-limits, or "" when it is a public internet address.

    Two rules, deliberately overlapping. The explicit network list names the
    ranges we care about so the reason a range is here stays readable. The
    ``is_global`` fallback catches everything the list forgets — 0.0.0.0/8,
    TEST-NET, multicast, and the IPv6 ranges nobody thinks about — because the
    thing we actually want is "refuse anything that is not the public
    internet", and enumerating the complement of that is a losing game.
    """
    # ::ffff:127.0.0.1 is loopback wearing an IPv6 costume; judge the real one.
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped

    for network in _BLOCKED_NETWORKS:
        if addr in network:
            return f"{addr} is in the private/reserved range {network}"
    if not addr.is_global:
        return f"{addr} is not a public internet address"
    return ""


def validate_public_url(url: str) -> None:
    """Raise SSRFError if *url* is obviously not a public http(s) address.

    Scheme, hostname denylist and bare-IP checks only — this does no DNS, so it
    is safe to call from sync code and cheap enough to run on user input before
    a client is even opened. It is NOT sufficient on its own: a hostname that
    resolves to a private address passes here. Every actual request goes through
    ``make_client``, whose request hook re-runs these checks against the
    resolved address, on the first request and on every redirect hop.
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
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return

    reason = _blocked_reason(addr)
    if reason:
        raise SSRFError(
            f"URL targets a private/reserved address ({reason}). "
            "Only public internet addresses are allowed."
        )


async def assert_public_url(url: str) -> None:
    """``validate_public_url`` plus a DNS check on the resolved addresses.

    The name-based checks cannot see the attack that matters: a hostname the
    attacker controls, pointed at 169.254.169.254 or a Railway 100.64/10
    neighbour. Resolving here and rejecting every non-public answer closes that,
    and closes it for redirect targets too because ``make_client`` runs this on
    every hop rather than only on the URL the caller passed in.

    A residual DNS-rebinding window remains — we resolve, then httpx resolves
    again to connect, and a hostile resolver can answer differently the second
    time. Closing that needs the connection pinned to the address we checked;
    the egress rules are the backstop until then.
    """
    validate_public_url(url)

    host = urlparse(url).hostname or ""
    try:
        ipaddress.ip_address(host)
        return  # a bare IP was already judged by validate_public_url
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve hostname {host!r}.") from exc

    if not infos:
        raise SSRFError(f"Hostname {host!r} resolved to no addresses.")

    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        reason = _blocked_reason(addr)
        if reason:
            raise SSRFError(
                f"Hostname {host!r} resolves to a private/reserved address "
                f"({reason}). Only public internet addresses are allowed."
            )


async def _guard_request(request: httpx.Request) -> None:
    """httpx request hook: refuse a request to a non-public address.

    Mounted on every client from ``make_client``. httpx fires this for each
    request it makes, redirects included, which is the point: validating only
    the caller's URL let a 302 to http://169.254.169.254/ through, and the
    response body came back to the caller.
    """
    try:
        await assert_public_url(str(request.url))
    except SSRFError:
        logger.warning("fetch: refused request to non-public address %s", request.url)
        raise


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=_HEADERS,
        timeout=_TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
        trust_env=False,
        event_hooks={"request": [_guard_request]},
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
