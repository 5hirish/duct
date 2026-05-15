"""Short-lived exchange codes for delivering JWTs without exposing them in URLs.

Instead of redirecting to /?token=JWT (which leaks into browser history, server
logs, and Referer headers), the sign-in callback stores the JWT under an opaque
60-second single-use code and redirects to /?auth_code=CODE. The frontend calls
GET /auth/exchange?code=CODE to receive the JWT in a JSON body.
"""

from __future__ import annotations

import secrets
import time

_store: dict[str, tuple[str, float]] = {}  # code → (jwt, issued_at)
_TTL = 60  # seconds


def store_exchange_code(jwt: str) -> str:
    """Store a JWT and return a single-use opaque code (valid for 60 s)."""
    _purge_expired()
    code = secrets.token_urlsafe(32)
    _store[code] = (jwt, time.monotonic())
    return code


def consume_exchange_code(code: str) -> str | None:
    """Return the JWT for a valid, unexpired code and delete it. Returns None if invalid."""
    _purge_expired()
    entry = _store.pop(code, None)
    if entry is None:
        return None
    jwt, issued_at = entry
    if time.monotonic() - issued_at > _TTL:
        return None
    return jwt


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [k for k, (_, issued_at) in _store.items() if now - issued_at > _TTL]
    for k in expired:
        _store.pop(k, None)
