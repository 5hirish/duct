"""Google OAuth for Google Ads API (offline refresh token)."""

from __future__ import annotations

import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from config import get_configs

router = APIRouter(tags=["auth"])

OAUTH_STATE_TTL_SECONDS = 300
_oauth_states: dict[str, float] = {}


def _flow_from_env(*, state: str | None = None) -> Flow:
    cfg = get_configs()
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Missing GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET backend env vars.",
        )
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": cfg.google_oauth_client_id,
                "client_secret": cfg.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/adwords"],
        state=state,
    )
    flow.redirect_uri = cfg.google_oauth_redirect_uri
    return flow


def _is_valid_oauth_state(state: str) -> bool:
    issued_at = _oauth_states.pop(state, None)
    if issued_at is None:
        return False
    return (time.time() - issued_at) <= OAUTH_STATE_TTL_SECONDS


@router.get("/auth/google/authorize")
def google_authorize() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    flow = _flow_from_env(state=state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url=auth_url, status_code=307)


@router.get("/auth/google/callback")
def google_callback(code: str = Query(default=""), state: str = Query(default="")) -> RedirectResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code.")
    if not state or not _is_valid_oauth_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    flow = _flow_from_env(state=state)
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
