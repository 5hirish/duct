"""Fetching a URL that somebody else chose.

A saved TikTok reference carries cover and slide URLs that came out of an Apify
run and then through the browser, so by the time the server sees them they are
whatever the request said. Fetching one is a request the caller gets to aim,
and the classic ways to aim it are at our own network: cloud metadata on
169.254.169.254, a loopback admin port, a private address behind a redirect.

The guard here is an allowlist, not a blocklist of private ranges. Every hop
must be ``https``, on the default port, to a hostname under a domain the caller
names. That closes the internal-address class without resolving DNS ourselves:
an IP literal never matches a domain, and nobody but the domain's owner can
point ``*.tiktokcdn.com`` at 10.0.0.1. A resolve-then-check filter would add a
lookup per fetch and still lose to the client re-resolving at connect time.

Redirects are followed by hand so each ``Location`` is held to the same rule,
and headers the caller attached (an Apify token) are dropped the moment a hop
leaves the host they were meant for. The body is streamed against a byte cap
and its content type checked before a byte is kept.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

# A CDN may bounce once or twice between edges; more than this is a loop or a
# chain someone built on purpose.
MAX_REDIRECTS = 3


class FetchRefused(Exception):
    """The URL, a redirect, the response, or the transport broke a rule.

    One type for all of them because the caller's decision is the same — this
    source yields nothing — and the message says which rule for the log.
    """


@dataclass(frozen=True)
class Fetched:
    data: bytes
    content_type: str  # the media type alone, lowercased, parameters stripped


def host_on_allowlist(host: str, domains: Collection[str]) -> bool:
    """True when *host* is one of *domains* or a subdomain of one.

    Matched on a dot boundary, never as a substring: ``eviltiktokcdn.com`` and
    ``tiktokcdn.com.attacker.net`` both end in the right letters.
    """
    host = host.rstrip(".").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def check_url(url: str, domains: Collection[str]) -> str:
    """Return the URL's hostname if it may be fetched, else raise FetchRefused."""
    try:
        parts = urlsplit(url)
        port = parts.port  # raises on a malformed port
    except ValueError as exc:
        raise FetchRefused(f"unparseable URL: {exc}") from exc
    if parts.scheme != "https":
        raise FetchRefused(f"scheme {parts.scheme or '(none)'} is not https")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise FetchRefused("no host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise FetchRefused(f"IP literal {host}")
    if port not in (None, 443):
        raise FetchRefused(f"non-default port {port} on {host}")
    if not host_on_allowlist(host, domains):
        raise FetchRefused(f"host {host} is not on the allowlist")
    return host


def fetch_allowlisted(
    client: httpx.Client,
    url: str,
    *,
    domains: Collection[str],
    content_types: Collection[str],
    max_bytes: int,
    headers: Mapping[str, str] | None = None,
) -> Fetched:
    """GET *url* under the rules above and return its body.

    ``headers`` go only to the host of *url* itself; a redirect elsewhere loses
    them, which is what keeps a token from following a bounce to a stranger.
    Raises FetchRefused for every failure, transport errors included.
    """
    origin_host = check_url(url, domains)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        host = check_url(current, domains)
        send = dict(headers or {}) if host == origin_host else {}
        try:
            with client.stream("GET", current, headers=send, follow_redirects=False) as resp:
                if resp.is_redirect:  # httpx only says so when a Location is present
                    current = str(httpx.URL(current).join(resp.headers["location"]))
                    continue
                if resp.status_code != httpx.codes.OK:
                    raise FetchRefused(f"HTTP {resp.status_code} from {host}")
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type not in content_types:
                    raise FetchRefused(f"content type {content_type or '(none)'} from {host}")
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise FetchRefused(f"{declared} bytes from {host} is over {max_bytes}")
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body += chunk
                    # Checked while streaming because Content-Length is optional
                    # and a chunked response can simply not stop.
                    if len(body) > max_bytes:
                        raise FetchRefused(f"body from {host} passed {max_bytes} bytes")
                return Fetched(bytes(body), content_type)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:  # InvalidURL: a Location that is not a URL
            raise FetchRefused(f"transport error from {host}: {type(exc).__name__}") from exc
    raise FetchRefused(f"more than {MAX_REDIRECTS} redirects from {origin_host}")
