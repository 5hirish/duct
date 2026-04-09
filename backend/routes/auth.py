"""OAuth entrypoints keyed by connector_id (browser flow; no API key on these routes)."""

from __future__ import annotations

import secrets
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_501_NOT_IMPLEMENTED

from config import get_configs
from service.connectors import get_connector, normalize_connector_id
from service.google.constants import GA4_CONNECTOR_ID, GOOGLE_ADS_CONNECTOR_ID, GSC_CONNECTOR_ID
from service.google.oauth import create_google_oauth_flow
from service.oauthstate import cleanup_expired_states, consume_state, save_state

router = APIRouter(tags=["auth"])

OAUTH_STATE_TTL_SECONDS = 300
CONNECTOR_FLOW_GOOGLE_ADS = "connector_google_ads"
CONNECTOR_FLOW_GA4 = "connector_ga4"
CONNECTOR_FLOW_GSC = "connector_gsc"


def _no_store_redirect(url: str, status_code: int = 307) -> RedirectResponse:
    """Build a redirect response that disables client/proxy caching."""
    response = RedirectResponse(url=url, status_code=status_code)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _google_connector_authorize(connector_id: str, flow_key: str) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    try:
        meta, _ = get_connector(connector_id)
        scope = meta.oauth_scope
        if not scope:
            raise ValueError(f"Connector {connector_id!r} is missing oauth scope.")
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
    cleanup_expired_states()
    save_state(state, flow.code_verifier, flow_key, OAUTH_STATE_TTL_SECONDS)
    return _no_store_redirect(auth_url, status_code=307)


def _google_connector_callback(
    *,
    connector_id: str,
    code: str,
    state: str,
    flow_key: str,
    token_fragment_key: str,
) -> RedirectResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code.")
    if not state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
    ok, code_verifier = consume_state(state, flow_key, OAUTH_STATE_TTL_SECONDS)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    try:
        meta, _ = get_connector(connector_id)
        scope = meta.oauth_scope
        if not scope:
            raise ValueError(f"Connector {connector_id!r} is missing oauth scope.")
        flow = create_google_oauth_flow(state=state, scopes=[scope])
        if code_verifier is not None:
            flow.code_verifier = code_verifier
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
        f"{get_configs().frontend_origin}/connections#{token_fragment_key}={quote(refresh_token, safe='')}"
    )
    return _no_store_redirect(redirect_url, status_code=307)


def _google_ads_authorize() -> RedirectResponse:
    return _google_connector_authorize(GOOGLE_ADS_CONNECTOR_ID, CONNECTOR_FLOW_GOOGLE_ADS)


def _ga4_authorize() -> RedirectResponse:
    return _google_connector_authorize(GA4_CONNECTOR_ID, CONNECTOR_FLOW_GA4)


def _gsc_authorize() -> RedirectResponse:
    return _google_connector_authorize(GSC_CONNECTOR_ID, CONNECTOR_FLOW_GSC)


def _google_ads_callback(code: str, state: str) -> RedirectResponse:
    return _google_connector_callback(
        connector_id=GOOGLE_ADS_CONNECTOR_ID,
        code=code,
        state=state,
        flow_key=CONNECTOR_FLOW_GOOGLE_ADS,
        token_fragment_key="refresh_token",
    )


def _ga4_callback(code: str, state: str) -> RedirectResponse:
    return _google_connector_callback(
        connector_id=GA4_CONNECTOR_ID,
        code=code,
        state=state,
        flow_key=CONNECTOR_FLOW_GA4,
        token_fragment_key="ga4_refresh_token",
    )


def _gsc_callback(code: str, state: str) -> RedirectResponse:
    return _google_connector_callback(
        connector_id=GSC_CONNECTOR_ID,
        code=code,
        state=state,
        flow_key=CONNECTOR_FLOW_GSC,
        token_fragment_key="gsc_refresh_token",
    )


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
    if cid == GA4_CONNECTOR_ID:
        return _ga4_authorize()
    if cid == GSC_CONNECTOR_ID:
        return _gsc_authorize()

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
    if cid == GA4_CONNECTOR_ID:
        return _ga4_callback(code, state)
    if cid == GSC_CONNECTOR_ID:
        return _gsc_callback(code, state)

    raise HTTPException(
        status_code=HTTP_501_NOT_IMPLEMENTED,
        detail=f"Connector {cid!r} does not support OAuth yet.",
    )


@router.get("/auth/google/callback")
def google_oauth_callback_short_path(
    code: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    """Same handler as ``/auth/connectors/google_ads/oauth/callback`` for shorter redirect URIs."""
    return _google_ads_callback(code, state)
