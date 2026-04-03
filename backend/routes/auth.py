"""OAuth entrypoints keyed by connector_id (browser flow; no API key on these routes)."""

from __future__ import annotations

import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_501_NOT_IMPLEMENTED

from config import get_configs
from service.connectors import get_connector, normalize_connector_id
from service.google.constants import GOOGLE_ADS_CONNECTOR_ID
from service.google.oauth import create_google_oauth_flow

router = APIRouter(tags=["auth"])

OAUTH_STATE_TTL_SECONDS = 300
_oauth_states: dict[str, float] = {}


def _is_valid_oauth_state(state: str) -> bool:
    issued_at = _oauth_states.pop(state, None)
    if issued_at is None:
        return False
    return (time.time() - issued_at) <= OAUTH_STATE_TTL_SECONDS


def _google_ads_authorize() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    try:
        meta, _ = get_connector(GOOGLE_ADS_CONNECTOR_ID)
        scope = meta.oauth_scope or "https://www.googleapis.com/auth/adwords"
        flow = create_google_oauth_flow(state=state, scopes=[scope])
    except KeyError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Unknown connector",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url=auth_url, status_code=307)


def _google_ads_callback(code: str, state: str) -> RedirectResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code.")
    if not state or not _is_valid_oauth_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    try:
        meta, _ = get_connector(GOOGLE_ADS_CONNECTOR_ID)
        scope = meta.oauth_scope or "https://www.googleapis.com/auth/adwords"
        flow = create_google_oauth_flow(state=state, scopes=[scope])
    except KeyError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Unknown connector",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # pragma: no cover - upstream oauth errors vary
        raise HTTPException(status_code=502, detail=f"OAuth token exchange failed: {exc}") from exc

    refresh_token = (flow.credentials.refresh_token or "").strip()
    if not refresh_token:
        raise HTTPException(
            status_code=502,
            detail="No refresh token returned by Google. Re-consent is required.",
        )

    redirect_url = (
        f"{get_configs().frontend_origin}/connections#refresh_token={quote(refresh_token, safe='')}"
    )
    return RedirectResponse(url=redirect_url, status_code=307)


@router.get("/auth/connectors/{connector_id}/oauth/authorize")
def connector_oauth_authorize(connector_id: str) -> RedirectResponse:
    """Start OAuth for a connector that supports it (e.g. ``google_ads``)."""
    cid = normalize_connector_id(connector_id)
    try:
        meta, _ = get_connector(cid)
    except KeyError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Unknown connector",
        ) from exc

    if cid == GOOGLE_ADS_CONNECTOR_ID:
        return _google_ads_authorize()

    if meta.oauth_scope:
        raise HTTPException(
            status_code=HTTP_501_NOT_IMPLEMENTED,
            detail=f"OAuth for connector {cid!r} is not implemented yet.",
        )
    raise HTTPException(
        status_code=HTTP_501_NOT_IMPLEMENTED,
        detail=f"Connector {cid!r} does not support OAuth.",
    )


@router.get("/auth/connectors/{connector_id}/oauth/callback")
def connector_oauth_callback(
    connector_id: str,
    code: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    """OAuth redirect target registered in the Google Cloud console."""
    cid = normalize_connector_id(connector_id)
    try:
        get_connector(cid)
    except KeyError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Unknown connector",
        ) from exc

    if cid == GOOGLE_ADS_CONNECTOR_ID:
        return _google_ads_callback(code, state)

    raise HTTPException(
        status_code=HTTP_501_NOT_IMPLEMENTED,
        detail=f"Connector {cid!r} does not support OAuth yet.",
    )
