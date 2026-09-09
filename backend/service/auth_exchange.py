"""Short-lived exchange codes for handing secrets to a client without a URL leak.

Three things need this, for the same reason: an OAuth step ends as a *browser
redirect*, and anything in that URL lands in browser history, server logs and
Referer headers.

* **Sign-in** — the JWT. Instead of `/?token=JWT`, the callback stores it under
  an opaque 60-second single-use code and redirects to `/?auth_code=CODE`; the
  frontend calls `GET /auth/exchange?code=CODE` for the token itself.
* **Desktop connector OAuth** — the connector's refresh token. That flow runs in
  the *system browser* and comes back through a custom-scheme deep link, so the
  redirect URL is even more exposed than a same-browser one. The token never
  rides in it; a code does.
* **Guest link** — the other direction. A guest starting Google sign-in must
  say which guest to link, but the authorize endpoint is a bare navigation
  with no bearer token, so the guest's JWT cannot travel with it and must not
  ride the URL. The guest mints a link code first and the URL carries that.
  Five minutes rather than sixty seconds: the code is redeemed *before*
  Google, and between minting it and clicking the button the user may read
  the page.

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
_NS_LINK = "link"

_store: dict[str, tuple[str, Any, float]] = {}  # code → (namespace, payload, issued_at)
_TTL = 60  # seconds
_LINK_TTL = 300  # seconds
_TTL_BY_NAMESPACE = {_NS_SIGNIN: _TTL, _NS_CONNECTOR: _TTL, _NS_LINK: _LINK_TTL}


def _ttl_for(namespace: str) -> float:
    return _TTL_BY_NAMESPACE.get(namespace, _TTL)


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
    if time.monotonic() - issued_at > _ttl_for(namespace):
        return None
    return payload


def store_exchange_code(jwt: str) -> str:
    """Store a JWT and return a single-use opaque code (valid for 60 s)."""
    return _store_code(_NS_SIGNIN, jwt)


def consume_exchange_code(code: str) -> str | None:
    """Return the JWT for a valid, unexpired code and delete it. Returns None if invalid."""
    payload = _consume_code(_NS_SIGNIN, code)
    return payload if isinstance(payload, str) else None


def store_connector_code(
    *, connector_type: str, refresh_token: str, granted_scopes: str = ""
) -> str:
    """Store a connector's OAuth refresh token; return a single-use opaque code.

    ``granted_scopes`` travels with the token rather than being looked up later:
    it is a property of this particular consent, and the next reconnect can
    grant something different.
    """
    return _store_code(
        _NS_CONNECTOR,
        {
            "connector_type": connector_type,
            "refresh_token": refresh_token,
            "granted_scopes": granted_scopes,
        },
    )


def consume_connector_code(code: str) -> dict[str, str] | None:
    """Return `{connector_type, refresh_token, granted_scopes}` for a valid code."""
    payload = _consume_code(_NS_CONNECTOR, code)
    return payload if isinstance(payload, dict) else None


def store_link_code(user_id: str) -> str:
    """Store the guest a sign-in should link to; return a single-use code (5 min)."""
    return _store_code(_NS_LINK, str(user_id))


def consume_link_code(code: str) -> str | None:
    """Return the guest user id for a valid link code and delete it."""
    payload = _consume_code(_NS_LINK, code)
    return payload if isinstance(payload, str) else None


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [
        k
        for k, (namespace, _, issued_at) in _store.items()
        if now - issued_at > _ttl_for(namespace)
    ]
    for k in expired:
        _store.pop(k, None)
