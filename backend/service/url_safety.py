"""SSRF guards for server-side URL fetches.

Any URL that comes from model/agent input or a third-party API response (e.g.
Apify ``mediaUrls``) must be validated before the backend fetches it, so a
crafted URL can't make us hit internal/link-local addresses (cloud metadata,
localhost) or leak a secret to an attacker-controlled host. Trusted first-party
URLs (our own R2/CDN, local ``/uploads`` paths) should NOT be run through these
— they may be relative and are not attacker-influenced.
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
    pinned, pre-validated IP. The only current sink is Gemini video understanding,
    which returns empty for non-video bytes, so the residual is blind SSRF."""
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


def safe_get_bytes(url: str) -> bytes | None:
    """Fetch bytes from an UNTRUSTED URL with SSRF guards. Use this (not
    storage.get_bytes, which follows redirects blindly) for agent/third-party URLs.

    Closes the redirect bypass: redirects are NOT auto-followed; each hop's target
    is re-validated with is_public_http_url before we follow it (a validated URL
    can otherwise 302 straight to an internal host). Returns None on any failure.

    Residual: the initial connect still re-resolves DNS, so a narrow rebinding race
    remains (see is_public_http_url) — acceptable here because the only consumer is
    Gemini video analysis (non-video bytes ⇒ empty), making this blind SSRF."""
    import httpx

    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        if not is_public_http_url(current):
            return None
        try:
            resp = httpx.get(current, timeout=_FETCH_TIMEOUT_SECS, follow_redirects=False)
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
