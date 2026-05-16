"""User sign-in via Google OAuth (identity, not data-source access)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from config import get_configs
from service.auth_exchange import consume_exchange_code, store_exchange_code
from service.google.oauth import create_google_signin_flow
from service.oauthstate import cleanup_expired_states, consume_state, save_state
from service.user_store import upsert_google_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signin"])

OAUTH_STATE_TTL_SECONDS = 300
SIGNIN_FLOW = "signin_google"

JWT_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _no_store_redirect(url: str, status_code: int = 307) -> RedirectResponse:
    """Build a redirect response that disables client/proxy caching."""
    response = RedirectResponse(url=url, status_code=status_code)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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
    cleanup_expired_states()
    save_state(state, flow.code_verifier, SIGNIN_FLOW, OAUTH_STATE_TTL_SECONDS)
    return _no_store_redirect(auth_url, status_code=307)


@router.get("/auth/signin/google/callback")
def signin_google_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    """Google OAuth callback for user sign-in. Exchanges code, creates JWT, redirects to app."""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state.")
    ok, code_verifier = consume_state(state, SIGNIN_FLOW, OAUTH_STATE_TTL_SECONDS)
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
        logger.exception("OAuth token exchange failed")
        raise HTTPException(status_code=502, detail="OAuth token exchange failed.") from exc

    creds = flow.credentials
    if not creds or not creds.id_token:
        raise HTTPException(status_code=502, detail="No ID token returned by Google.")

    # id_token is already decoded by google-auth when fetched via the flow
    id_info = creds.id_token if isinstance(creds.id_token, dict) else {}
    if not id_info:
        # Fallback: verify/decode the raw OIDC ID token string.
        try:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests

            id_info = google_id_token.verify_oauth2_token(
                str(creds.id_token), google_requests.Request(), get_configs().google_oauth_client_id
            )
        except Exception as exc:
            logger.exception("Failed to verify Google ID token")
            raise HTTPException(status_code=502, detail="Failed to verify ID token.") from exc

    provider_user_id = id_info.get("sub", "")
    email = id_info.get("email", "")
    name = id_info.get("name", "")
    picture = id_info.get("picture", "")

    if not provider_user_id or not email:
        raise HTTPException(
            status_code=502, detail="Google ID token missing required identity fields."
        )
    normalized_email = email.strip().lower()

    upsert_google_user(
        provider_user_id=provider_user_id,
        email=normalized_email,
        name=name,
        picture=picture,
        raw_profile={
            "sub": provider_user_id,
            "email": normalized_email,
            "name": name,
            "picture": picture,
        },
    )

    try:
        token = _create_jwt(normalized_email, name, picture)
    except ValueError as exc:
        logger.exception("JWT creation failed")
        raise HTTPException(status_code=500, detail="Authentication error.") from exc

    # C1 fix: deliver JWT via a short-lived exchange code so it never appears in
    # the URL query string (browser history, server logs, Referer headers).
    auth_code = store_exchange_code(token)
    cfg = get_configs()
    redirect_url = f"{cfg.frontend_origin}/?auth_code={auth_code}"
    return _no_store_redirect(redirect_url, status_code=307)


@router.get("/auth/exchange")
def exchange_auth_code(code: str = Query(default="")) -> dict:
    """Single-use endpoint: exchange a 60-second auth code for the JWT.

    The frontend calls this immediately after the OAuth redirect, stores the
    returned token in localStorage, then discards the code from the URL.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing auth code.")
    token = consume_exchange_code(code)
    if token is None:
        raise HTTPException(status_code=400, detail="Invalid or expired auth code.")
    return {"token": token}
