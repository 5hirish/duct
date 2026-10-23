"""Connecting an MCP server: the Connections page's half, and the OAuth callback.

The connect is GitHub's shape (``routes/auth.py``) for a server the user names:

1. ``POST /api/user/mcp/servers`` (signed in). With a key, probe and save. With
   none, ask the server what it needs: nothing (probe and save), a sign-in
   Duct can start (discover, register, park the flow under the OAuth
   ``state``, return the authorize URL), or a sign-in it cannot (``needs_key``,
   and the page asks for one).
2. The browser, or the desktop shell's system browser, signs in at the vendor.
3. ``GET /auth/mcp/callback`` (no session: a redirect carries none) trades the
   code for tokens and parks them as a grant for the user who started step 1.
4. ``POST /api/user/mcp/claim`` (signed in) stores the grant, and only for that
   same user. The callback is a URL anyone can be sent to; binding the store
   to the signed-in session is what stops a stranger's sign-in landing in
   your account, or yours in theirs.

The client metadata document is public: an authorization server fetches it,
with no key, when our ``client_id`` is its URL.
"""

from __future__ import annotations

import logging
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND, HTTP_502_BAD_GATEWAY

from config import get_configs
from db.session import get_session
from models.auth import User
from service.auth import get_current_user
from service.auth_exchange import (
    consume_mcp_flow,
    consume_mcp_grant,
    store_mcp_flow,
    store_mcp_grant,
)
from service.mcp import client as mcp_client
from service.mcp import oauth
from service.mcp import store as mcp_store
from service.mcp.http import UnsafeServerUrl, canonical_url
from service.mcp.presets import PRESETS, preset
from service.ratelimit import RateLimit, client_address

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])
oauth_router = APIRouter(tags=["mcp"])

CLIENT_DESKTOP = "desktop"
# What the app reads off the return URL. Coarse on purpose: it is visible and
# pasteable, so it names the kind of failure, never the server's words.
CONNECTOR_PARAM = "mcp"
ERROR_EXPIRED = "expired"
ERROR_CONSENT = "consent"
ERROR_EXCHANGE = "exchange"

STATUS_CONNECTED = "connected"
STATUS_AUTHORIZE = "authorize"
STATUS_NEEDS_KEY = "needs_key"

# Each connect start makes outbound requests to addresses the caller chose
# (the server, then wherever its metadata points). Per user and per address,
# like every route that spends before the caller has proven much.
_CONNECT_LIMIT_USER = RateLimit(limit=20, window_seconds=600.0)
_CONNECT_LIMIT_ADDRESS = RateLimit(limit=40, window_seconds=600.0)


class ServerIn(BaseModel):
    url: str = ""
    preset: str = ""
    name: str = ""
    api_key: str = ""
    # Where the sign-in should come home to: the web app's own tab, or the
    # desktop shell through its relay page.
    client: str = ""


class ClaimIn(BaseModel):
    code: str


def _limit(request: Request, user: User) -> None:
    detail = "Too many connection attempts. Try again in a few minutes."
    _CONNECT_LIMIT_USER.enforce(str(user.id), detail)
    _CONNECT_LIMIT_ADDRESS.enforce(client_address(request), detail)


def _server_out(db: Session, user_id: UUID, row_id: UUID) -> dict:
    return next(s for s in mcp_store.list_servers(db, user_id) if s["id"] == str(row_id))


def _resolve_url(body: ServerIn) -> tuple[str, str]:
    chosen = preset(body.preset) if body.preset else None
    if body.preset and chosen is None:
        raise HTTPException(status_code=422, detail="Unknown server.")
    try:
        url = canonical_url(chosen.url if chosen else body.url)
    except UnsafeServerUrl as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return url, (body.name.strip() or (chosen.label if chosen else mcp_store.default_name(url)))


def _save(db: Session, user: User, *, url: str, name: str, credentials: dict, validated: bool) -> dict:
    row = mcp_store.save_server(
        db, user_id=user.id, url=url, name=name, credentials=credentials, validated=validated
    )
    db.commit()
    db.refresh(row)
    return _server_out(db, user.id, row.id)


async def _probe(*, url: str, name: str, credentials: dict) -> None:
    """List the server's tools with these credentials, or raise ``McpCallError``."""
    access = mcp_store.ServerAccess(row_id=None, key="", url=url, name=name, credentials=credentials)
    await mcp_client.probe(access)


@router.get("/presets")
def list_presets(user: User = Depends(get_current_user)) -> dict:
    return {"presets": [p.as_dict() for p in PRESETS]}


@router.get("/servers")
def list_servers(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    return {"servers": mcp_store.list_servers(db, user.id)}


@router.post("/servers")
async def connect_server(
    body: ServerIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    _limit(request, user)
    url, name = _resolve_url(body)

    if body.api_key.strip():
        credentials = mcp_store.key_credentials(body.api_key.strip())
        try:
            await _probe(url=url, name=name, credentials=credentials)
        except mcp_client.McpCallError as exc:
            if exc.code == mcp_client.CODE_REAUTH:
                raise HTTPException(status_code=422, detail=f"{name} refused that key.") from exc
            raise HTTPException(status_code=HTTP_502_BAD_GATEWAY, detail=exc.message) from exc
        server = _save(db, user, url=url, name=name, credentials=credentials, validated=True)
        return {"status": STATUS_CONNECTED, "server": server}

    try:
        plan = await oauth.discover(url)
        if plan.kind == oauth.AUTH_NONE:
            credentials = mcp_store.no_credentials()
            try:
                await _probe(url=url, name=name, credentials=credentials)
            except mcp_client.McpCallError as exc:
                if exc.code == mcp_client.CODE_REAUTH:
                    # It let an anonymous initialize through and then wanted
                    # credentials for the tools: a key server that says so late.
                    return {"status": STATUS_NEEDS_KEY, "message": exc.message}
                raise HTTPException(status_code=HTTP_502_BAD_GATEWAY, detail=exc.message) from exc
            server = _save(db, user, url=url, name=name, credentials=credentials, validated=True)
            return {"status": STATUS_CONNECTED, "server": server}
        registration = await oauth.register(plan)
    except oauth.OAuthUnavailable as exc:
        logger.info("mcp connect: %s needs a key (%s)", url, exc)
        return {"status": STATUS_NEEDS_KEY, "message": str(exc)}
    except oauth.OAuthFailed as exc:
        raise HTTPException(status_code=HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    verifier, challenge = oauth.new_pkce()
    state = store_mcp_flow({
        "user_id": str(user.id),
        "url": url,
        "name": name,
        "desktop": body.client == CLIENT_DESKTOP,
        "verifier": verifier,
        "client_id": registration.client_id,
        "client_secret": registration.client_secret,
        "auth_method": registration.auth_method,
        "token_endpoint": plan.token_endpoint,
        "resource": plan.resource,
        "issuer": plan.issuer,
    })
    return {
        "status": STATUS_AUTHORIZE,
        "authorize_url": oauth.authorize_url(plan, registration, state=state, challenge=challenge),
    }


@router.post("/claim")
async def claim_grant(
    body: ClaimIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Store a finished sign-in, for the user who started it and no one else.

    Someone else's code answers exactly as an expired one, and is spent
    either way.
    """
    payload = consume_mcp_grant(body.code.strip())
    if payload is None or payload.get("user_id") != str(user.id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="That connection expired or was started from another account. Connect again.",
        )
    grant = payload.get("grant") or {}
    url, name, credentials = grant["url"], grant["name"], grant["credentials"]
    # A grant is kept even when the server is down this minute: the user just
    # signed in, and making them do it again for a vendor's blip is the worse
    # failure. A token refused straight after sign-in is not kept.
    validated = True
    try:
        await _probe(url=url, name=name, credentials=credentials)
    except mcp_client.McpCallError as exc:
        if exc.code == mcp_client.CODE_REAUTH:
            raise HTTPException(status_code=422, detail=f"{name} refused the sign-in. Connect again.") from exc
        logger.warning("mcp claim: %s did not answer the first listing: %s", url, exc.message)
        validated = False
    return {"server": _save(db, user, url=url, name=name, credentials=credentials, validated=validated)}


@router.delete("/servers/{server_id}", status_code=204)
def delete_server(
    server_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> Response:
    if not mcp_store.delete_server(db, user.id, server_id):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No such server.")
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# The browser's half: no session, no API key
# ---------------------------------------------------------------------------


def _home(*, desktop: bool, query: str) -> RedirectResponse:
    page = "desktop-auth" if desktop else "connections"
    response = RedirectResponse(f"{get_configs().frontend_origin}/{page}?{query}", status_code=307)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


def _fail(reason: str, *, desktop: bool) -> RedirectResponse:
    return _home(desktop=desktop, query=f"connector={CONNECTOR_PARAM}&error={reason}")


@oauth_router.get(oauth.CLIENT_METADATA_PATH)
def client_metadata() -> JSONResponse:
    return JSONResponse(
        oauth.client_metadata_document(),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@oauth_router.get(oauth.CALLBACK_PATH)
async def oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    iss: str = Query(default=""),
) -> RedirectResponse:
    flow = consume_mcp_flow(state) if state else None
    if flow is None:
        return _fail(ERROR_EXPIRED, desktop=get_configs().duct_local)
    desktop = bool(flow.get("desktop"))
    if error or not code:
        return _fail(ERROR_CONSENT, desktop=desktop)
    # RFC 9207: a server that names itself must be the one we started with,
    # or a code from a different authorization server is being replayed here.
    if iss and iss.rstrip("/") != str(flow.get("issuer") or "").rstrip("/"):
        logger.warning("mcp callback: issuer mismatch for %s", flow.get("url"))
        return _fail(ERROR_EXCHANGE, desktop=desktop)

    registration = oauth.ClientRegistration(
        client_id=flow["client_id"],
        client_secret=flow.get("client_secret") or "",
        auth_method=flow.get("auth_method") or "none",
    )
    try:
        tokens = await oauth.exchange_code(
            token_endpoint=flow["token_endpoint"],
            registration=registration,
            code=code,
            verifier=flow["verifier"],
            resource=flow["resource"],
        )
    except oauth.OAuthFailed as exc:
        logger.warning("mcp callback: exchange with %s failed: %s", flow.get("url"), exc)
        return _fail(ERROR_EXCHANGE, desktop=desktop)

    grant_code = store_mcp_grant(
        user_id=flow["user_id"],
        grant={
            "url": flow["url"],
            "name": flow["name"],
            "credentials": mcp_store.oauth_credentials(
                tokens=tokens,
                registration=registration,
                token_endpoint=flow["token_endpoint"],
                resource=flow["resource"],
                issuer=flow.get("issuer") or "",
            ),
        },
    )
    return _home(desktop=desktop, query=f"connector={CONNECTOR_PARAM}&auth_code={quote(grant_code, safe='')}")
