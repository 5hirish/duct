"""User sign-in via Google OAuth (identity, not data-source access)."""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from config import get_configs
from service.google.oauth import create_google_signin_flow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signin"])

OAUTH_STATE_TTL_SECONDS = 300
_signin_states: dict[str, tuple[float, str | None]] = {}

JWT_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _consume_state(state: str) -> tuple[bool, str | None]:
    entry = _signin_states.pop(state, None)
    if entry is None:
        return False, None
    issued_at, code_verifier = entry
    if (time.time() - issued_at) > OAUTH_STATE_TTL_SECONDS:
        return False, None
    return True, code_verifier


async def _verify_turnstile(token: str, remote_ip: str) -> bool:
    """Verify a Cloudflare Turnstile token. Returns True if valid."""
    cfg = get_configs()
    if not cfg.turnstile_secret_key:
        return True  # skip in dev when not configured
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": cfg.turnstile_secret_key,
                "response": token,
                "remoteip": remote_ip,
            },
        )
        result = resp.json()
        return result.get("success", False)


def _create_jwt(email: str, name: str, picture: str) -> str:
    cfg = get_configs()
    if not cfg.jwt_secret:
        raise ValueError("JWT_SECRET is not configured.")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "name": name,
        "picture": picture,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm="HS256")


@router.get("/auth/signin/google/authorize")
async def signin_google_authorize(
    request: Request,
    turnstile_token: str = Query(default=""),
) -> RedirectResponse:
    """Start Google OAuth for user sign-in."""
    if turnstile_token:
        client_ip = request.client.host if request.client else ""
        valid = await _verify_turnstile(turnstile_token, client_ip)
        if not valid:
            raise HTTPException(status_code=403, detail="Turnstile verification failed.")
    elif get_configs().turnstile_secret_key:
        raise HTTPException(status_code=400, detail="Turnstile token required.")

    state = secrets.token_urlsafe(32)
    try:
        flow = create_google_signin_flow(state=state)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    auth_url, _ = flow.authorization_url(
        access_type="online",
        include_granted_scopes="false",
        prompt="select_account",
    )
    _signin_states[state] = (time.time(), flow.code_verifier)
    return RedirectResponse(url=auth_url, status_code=307)


@router.get("/auth/signin/google/callback")
def signin_google_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    """Google OAuth callback for user sign-in. Exchanges code, creates JWT, redirects to app."""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state.")
    ok, code_verifier = _consume_state(state)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    try:
        flow = create_google_signin_flow(state=state)
        if code_verifier is not None:
            flow.code_verifier = code_verifier
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"OAuth token exchange failed: {exc}"
        ) from exc

    creds = flow.credentials
    if not creds or not creds.id_token:
        raise HTTPException(status_code=502, detail="No ID token returned by Google.")

    # id_token is already decoded by google-auth when fetched via the flow
    id_info = creds.id_token if isinstance(creds.id_token, dict) else {}
    if not id_info:
        # Fallback: decode from the raw token
        try:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests

            id_info = google_id_token.verify_oauth2_token(
                creds.token, google_requests.Request(), get_configs().google_oauth_client_id
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Failed to verify ID token: {exc}"
            ) from exc

    email = id_info.get("email", "")
    name = id_info.get("name", "")
    picture = id_info.get("picture", "")

    if not email:
        raise HTTPException(status_code=502, detail="No email in Google ID token.")

    try:
        token = _create_jwt(email, name, picture)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    cfg = get_configs()
    redirect_url = f"{cfg.frontend_origin}/?token={quote(token, safe='')}"
    return RedirectResponse(url=redirect_url, status_code=307)
