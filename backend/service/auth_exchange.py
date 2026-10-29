"""Short-lived exchange codes for handing secrets to a client without a URL leak.

Three things need this, for the same reason: an OAuth step ends as a *browser
redirect*, and anything in that URL lands in browser history, server logs and
Referer headers.

* **Sign-in** — the JWT. Instead of `/?token=JWT`, the callback stores it under
  an opaque 60-second single-use code and redirects to `/?auth_code=CODE`; the
  frontend calls `GET /auth/exchange?code=CODE` for the token itself.
* **Google connector connect** — GitHub's shape below, for a refresh token. The
  connect starts from a *connect link* naming the signed-in user, and the
  callback parks what Google granted for that user to claim. The token never
  rides a URL and never reaches a client: the browser, or the desktop shell's
  deep link, carries only the code, and the claim stores the token server-side.
* **Guest link** — the other direction. A guest starting Google sign-in must
  say which guest to link, but the authorize endpoint is a bare navigation
  with no bearer token, so the guest's JWT cannot travel with it and must not
  ride the URL. The guest mints a link code first and the URL carries that.
  Five minutes rather than sixty seconds: the code is redeemed *before*
  Google, and between minting it and clicking the button the user may read
  the page.

* **MCP server connect** — the same shape as GitHub's, for a server the user
  named. What the callback needs (the PKCE verifier, the client Duct
  registered, the token endpoint, the user) is parked under the OAuth
  ``state`` itself, ten minutes because a first sign-in at a vendor can mean
  creating an account; the tokens come back as a grant for the claim route,
  honoured only for the same user (``routes/mcp.py``).

* **GitHub App connect** — both directions at once. The authorize route is a
  bare navigation again, so the signed-in app first mints a *connect link*
  naming its user (five minutes, like the guest link). What comes back is a
  *grant*: the repositories GitHub says that user may read, parked for the
  claim route, which honours it only for the same user
  (`service/github/app.py` explains why that binding is the whole point).

Codes are namespaced so one kind can never be redeemed as the other: a connector
grant presented at `/auth/exchange` would otherwise be handed back as if it
were a session JWT.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

_NS_SIGNIN = "signin"
_NS_CONNECTOR_GRANT = "connector_grant"
_NS_LINK = "link"
_NS_CONNECT_LINK = "connect_link"
_NS_GITHUB_GRANT = "github_grant"
_NS_MCP_FLOW = "mcp_flow"
_NS_MCP_GRANT = "mcp_grant"

_store: dict[str, tuple[str, Any, float]] = {}  # code → (namespace, payload, issued_at)
_TTL = 60  # seconds
_LINK_TTL = 300  # seconds
# A grant crosses back into the desktop app through a deep link, which may
# have to wake the app first; a minute was enough for the connector code the
# same route carried before grants, and two leave room for a slow wake.
_GRANT_TTL = 120  # seconds
_MCP_FLOW_TTL = 600  # seconds
_TTL_BY_NAMESPACE = {
    _NS_SIGNIN: _TTL,
    _NS_CONNECTOR_GRANT: _GRANT_TTL,
    _NS_LINK: _LINK_TTL,
    _NS_CONNECT_LINK: _LINK_TTL,
    _NS_GITHUB_GRANT: _GRANT_TTL,
    _NS_MCP_FLOW: _MCP_FLOW_TTL,
    _NS_MCP_GRANT: _GRANT_TTL,
}


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


def store_connector_grant(
    *, user_id: str, connector_type: str, refresh_token: str, granted_scopes: str = ""
) -> str:
    """Park a connector's OAuth grant for ``user_id`` to claim; return a single-use code (2 min).

    ``granted_scopes`` travels with the token rather than being looked up later:
    it is a property of this particular consent, and the next reconnect can
    grant something different.
    """
    return _store_code(
        _NS_CONNECTOR_GRANT,
        {
            "user_id": str(user_id),
            "connector_type": connector_type,
            "refresh_token": refresh_token,
            "granted_scopes": granted_scopes,
        },
    )


def consume_connector_grant(code: str) -> dict[str, str] | None:
    """Return ``{user_id, connector_type, refresh_token, granted_scopes}`` and delete it.

    Spent whoever presents it, like a GitHub grant: the caller compares
    ``user_id`` with the session.
    """
    payload = _consume_code(_NS_CONNECTOR_GRANT, code)
    return payload if isinstance(payload, dict) else None


def store_link_code(user_id: str) -> str:
    """Store the guest a sign-in should link to; return a single-use code (5 min)."""
    return _store_code(_NS_LINK, str(user_id))


def consume_link_code(code: str) -> str | None:
    """Return the guest user id for a valid link code and delete it."""
    payload = _consume_code(_NS_LINK, code)
    return payload if isinstance(payload, str) else None


def store_connect_link_code(user_id: str) -> str:
    """Name the user a connector connect belongs to; return a single-use code (5 min)."""
    return _store_code(_NS_CONNECT_LINK, str(user_id))


def consume_connect_link_code(code: str) -> str | None:
    """Return the user id for a valid connect-link code and delete it."""
    payload = _consume_code(_NS_CONNECT_LINK, code)
    return payload if isinstance(payload, str) else None


def store_github_grant(*, user_id: str, grant: dict[str, Any]) -> str:
    """Park a GitHub App grant for ``user_id`` to claim; return a single-use code (2 min)."""
    return _store_code(_NS_GITHUB_GRANT, {"user_id": str(user_id), "grant": grant})


def consume_github_grant(code: str) -> dict[str, Any] | None:
    """Return ``{user_id, grant}`` for a valid code and delete it.

    Spent whoever presents it: the caller compares ``user_id`` with the
    session, and a code offered by the wrong account is no longer worth
    keeping for the right one.
    """
    payload = _consume_code(_NS_GITHUB_GRANT, code)
    return payload if isinstance(payload, dict) else None

def store_mcp_flow(flow: dict[str, Any]) -> str:
    """Park an MCP sign-in in progress; the returned code is its OAuth ``state`` (10 min)."""
    return _store_code(_NS_MCP_FLOW, dict(flow))


def consume_mcp_flow(state: str) -> dict[str, Any] | None:
    payload = _consume_code(_NS_MCP_FLOW, state)
    return payload if isinstance(payload, dict) else None


def store_mcp_grant(*, user_id: str, grant: dict[str, Any]) -> str:
    """Park what an MCP sign-in produced for ``user_id`` to claim (2 min)."""
    return _store_code(_NS_MCP_GRANT, {"user_id": str(user_id), "grant": grant})


def consume_mcp_grant(code: str) -> dict[str, Any] | None:
    payload = _consume_code(_NS_MCP_GRANT, code)
    return payload if isinstance(payload, dict) else None



def _purge_expired() -> None:
    now = time.monotonic()
    expired = [
        k
        for k, (namespace, _, issued_at) in _store.items()
        if now - issued_at > _ttl_for(namespace)
    ]
    for k in expired:
        _store.pop(k, None)
