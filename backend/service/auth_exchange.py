"""Short-lived exchange codes for handing secrets to a client without a URL leak.

Two things need this, for the same reason: an OAuth callback ends as a *browser
redirect*, and anything in that URL lands in browser history, server logs and
Referer headers.

* **Sign-in** — the JWT. Instead of `/?token=JWT`, the callback stores it under
  an opaque 60-second single-use code and redirects to `/?auth_code=CODE`; the
  frontend calls `GET /auth/exchange?code=CODE` for the token itself.
* **Desktop connector OAuth** — the connector's refresh token. That flow runs in
  the *system browser* and comes back through a custom-scheme deep link, so the
  redirect URL is even more exposed than a same-browser one. The token never
  rides in it; a code does.

Codes are namespaced so one kind can never be redeemed as the other: a connector
refresh token presented at `/auth/exchange` would otherwise be handed back as if
it were a session JWT.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

_NS_SIGNIN = "signin"
_NS_CONNECTOR = "connector"

_store: dict[str, tuple[str, Any, float]] = {}  # code → (namespace, payload, issued_at)
_TTL = 60  # seconds


def _store_code(namespace: str, payload: Any) -> str:
    _purge_expired()
    code = secrets.token_urlsafe(32)
    _store[code] = (namespace, payload, time.monotonic())
    return code


def _consume_code(namespace: str, code: str) -> Any | None:
    _purge_expired()
    entry = _store.get(code)
    if entry is None:
        return None
    stored_namespace, payload, issued_at = entry
    if stored_namespace != namespace:
        # Wrong kind of code — leave it in place so its real owner can still
        # redeem it, and so probing one endpoint cannot burn the other's codes.
        return None
    _store.pop(code, None)
    if time.monotonic() - issued_at > _TTL:
        return None
    return payload


def store_exchange_code(jwt: str) -> str:
    """Store a JWT and return a single-use opaque code (valid for 60 s)."""
    return _store_code(_NS_SIGNIN, jwt)


def consume_exchange_code(code: str) -> str | None:
    """Return the JWT for a valid, unexpired code and delete it. Returns None if invalid."""
    payload = _consume_code(_NS_SIGNIN, code)
    return payload if isinstance(payload, str) else None


def store_connector_code(*, connector_type: str, refresh_token: str) -> str:
    """Store a connector's OAuth refresh token; return a single-use opaque code."""
    return _store_code(_NS_CONNECTOR, {"connector_type": connector_type, "refresh_token": refresh_token})


def consume_connector_code(code: str) -> dict[str, str] | None:
    """Return `{connector_type, refresh_token}` for a valid code and delete it."""
    payload = _consume_code(_NS_CONNECTOR, code)
    return payload if isinstance(payload, dict) else None


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [k for k, (_, _, issued_at) in _store.items() if now - issued_at > _TTL]
    for k in expired:
        _store.pop(k, None)
