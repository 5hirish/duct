"""SSRF guards for server-side URL fetches.

Ported verbatim from the Duct backend (backend/service/url_safety.py). Any URL
that comes from a third-party API response (e.g. Apify ``mediaUrls``) must be
validated before we fetch it, so a crafted URL can't make us hit internal /
link-local addresses (cloud metadata, localhost) or leak a secret to an
attacker-controlled host.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Untrusted fetches follow at most this many redirects, re-validating each hop.
_MAX_REDIRECTS = 3
_FETCH_TIMEOUT_SECS = 20.0


def is_public_http_url(url: str) -> bool:
    """True only for an http(s) URL whose host is public (not private / loopback
    / link-local / reserved). IP literals are checked directly; hostnames are
    resolved best-effort and blocked if they point into a non-global range
    (resolution failure is NOT a block — the fetch will fail on its own, and
    offline tests still run).

    LIMITATION — this is a pre-flight filter, NOT rebinding-safe: the fetch layer
    re-resolves DNS, so a host that passes here could resolve to an internal IP at
    connect time (TOCTOU / DNS rebinding). For untrusted URLs use safe_get_bytes()
    (which also re-validates redirect hops); full protection needs connecting to a
    pinned, pre-validated IP."""
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        return False
    # IP literal → must be global.
    try:
        return bool(ipaddress.ip_address(host).is_global)
    except ValueError:
        pass  # a hostname, not an IP literal
    # Hostname → block if it resolves into a non-global range.
    try:
        for info in socket.getaddrinfo(host, None):
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
    except (socket.gaierror, UnicodeError, ValueError, OSError):
        pass
    return True


def host_in(url: str, allowed: set[str]) -> bool:
    """True iff the URL's hostname (exact, case-insensitive, trailing-dot
    stripped) is in ``allowed``. Use to gate appending a secret to a known host —
    never a substring check, which ``https://evil.com/?x=api.apify.com`` defeats."""
    try:
        host = (urlparse(url).hostname or "").rstrip(".").lower()
    except Exception:
        return False
    return host in allowed


def safe_get_bytes(url: str, *, timeout: float = _FETCH_TIMEOUT_SECS) -> bytes | None:
    """Fetch bytes from an UNTRUSTED URL with SSRF guards.

    Redirects are NOT auto-followed; each hop's target is re-validated with
    is_public_http_url before we follow it (a validated URL can otherwise 302
    straight to an internal host). Returns None on any failure. ``timeout`` is
    the per-request ceiling — pass a larger value for video downloads."""
    import httpx

    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        if not is_public_http_url(current):
            return None
        try:
            resp = httpx.get(current, timeout=timeout, follow_redirects=False)
        except Exception:
            logger.warning("safe_get_bytes: fetch failed", exc_info=True)
            return None
        if resp.is_redirect:
            loc = resp.headers.get("location")
            if not loc:
                return None
            current = str(httpx.URL(current).join(loc))  # re-validated next loop
            continue
        try:
            resp.raise_for_status()
        except Exception:
            return None
        return resp.content
    logger.warning("safe_get_bytes: too many redirects from %s", url)
    return None
