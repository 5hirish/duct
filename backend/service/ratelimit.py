"""Fixed-window limits for the routes that spend before a caller has proven much.

Some routes run before sign-in: guest creation, the lead-magnet capture, the
OAuth entry points, the crawl prefetch and the audit teaser. Others take a
user, but a guest is a user anyone can mint. Either way nothing else stands
between a script and a database row, a crawl of someone's site, or a model
call on Duct's key. A per-key window is enough: the cost we are bounding is
ours, not the caller's, and the honest failure is a 429 with a retry time
rather than a Turnstile the desktop shell cannot render.

In-process on purpose. A multi-replica deployment gets one window per
replica, which is a looser limit, not a wrong one; the moment the miss rate
says so this moves to the database, and not before.
"""

from __future__ import annotations

import ipaddress
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

# Past this many keys a window sweeps out the expired ones, so a stream of
# one-off addresses costs a bounded amount of memory rather than a leak.
_PRUNE_AT_KEYS = 10_000

# Cloudflare's published edge ranges (cloudflare.com/ips). The hosted API sits
# behind Cloudflare and then Railway's edge, so the peer Railway reports is a
# Cloudflare address and the caller is in CF-Connecting-IP. Cloudflare
# overwrites that header, but a request that reaches Railway some other way
# carries whatever its sender typed, so it is believed only from these ranges.
_CLOUDFLARE_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
        "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
        "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
        "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
        "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
    )
)


@dataclass
class RateLimit:
    """``limit`` events per ``window_seconds`` for each key."""

    limit: int
    window_seconds: float

    def __post_init__(self) -> None:
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Record one event for ``key``.

        Returns ``(allowed, retry_after_seconds)``; ``retry_after`` is zero when
        allowed.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            started, count = self._hits.get(key, (now, 0))
            if now - started >= self.window_seconds:
                started, count = now, 0
            if count >= self.limit:
                return False, max(0.0, self.window_seconds - (now - started))
            self._hits[key] = (started, count + 1)
            if len(self._hits) > _PRUNE_AT_KEYS:
                self._prune(now)
        return True, 0.0

    def enforce(self, key: str, detail: str) -> None:
        """Record one event for ``key``, or refuse it with the 429 every limited
        route answers. ``Retry-After`` rounds up, so a client that waits that
        long never lands back in the same window."""
        allowed, retry_after = self.allow(key)
        if not allowed:
            raise HTTPException(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    def _prune(self, now: float) -> None:
        stale = [k for k, (started, _) in self._hits.items() if now - started >= self.window_seconds]
        for k in stale:
            self._hits.pop(k, None)


def _ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def client_address(request: Request) -> str:
    """The address to hold a caller to, as far as the proxies in front say.

    ``request.client`` alone is Railway's proxy on the hosted API: uvicorn
    rewrites it from X-Forwarded-For only for peers in FORWARDED_ALLOW_IPS,
    which defaults to loopback and the start command does not set. Keyed on
    that, every per-address limit is one bucket for the whole internet.
    Railway's edge writes X-Real-IP itself, so the header is taken from a
    non-public peer (a proxy on our side) and ignored from a public one, which
    would be the caller vouching for itself.
    """
    peer = request.client.host if request.client else ""
    real_ip = request.headers.get("x-real-ip", "").strip()
    peer_ip = _ip(peer)
    if real_ip and not (peer_ip is not None and peer_ip.is_global):
        peer, peer_ip = real_ip, _ip(real_ip)
    if peer_ip is not None and any(peer_ip in net for net in _CLOUDFLARE_NETWORKS):
        peer = request.headers.get("cf-connecting-ip", "").strip() or peer
    return peer or "unknown"
