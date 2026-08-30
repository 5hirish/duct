"""User sign-in via Google OAuth (identity, not data-source access)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from config import get_configs
from service.auth_exchange import consume_exchange_code, store_exchange_code
from service.google.oauth import create_google_signin_flow
from service.oauthstate import (
    cleanup_expired_states,
    consume_state_for_flows,
    save_state,
)
from service.turnstile import verify_turnstile
from service.user_store import upsert_google_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signin"])

OAUTH_STATE_TTL_SECONDS = 300
SIGNIN_FLOW = "signin_google"
# Same sign-in flow initiated from the desktop shell: the OAuth dance runs in
# the user's browser, so the callback must hand the auth code back to the shell
# (via the app's /desktop-auth relay page) instead of the web login page. The
# distinct flow name rides in the existing state store — no schema change.
SIGNIN_DESKTOP_FLOW = "signin_google_desktop"

JWT_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _no_store_redirect(url: str, status_code: int = 307) -> RedirectResponse:
    """Build a redirect response that disables client/proxy caching."""
    response = RedirectResponse(url=url, status_code=status_code)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Reasons the relay page knows how to explain. Deliberately coarse and
# non-identifying: they end up in a URL the user can see and paste.
SIGNIN_ERROR_CONFIG = "config"
SIGNIN_ERROR_EXPIRED = "expired"
SIGNIN_ERROR_EXCHANGE = "exchange"
SIGNIN_ERROR_IDENTITY = "identity"
SIGNIN_ERROR_SERVER = "server"


def _signin_failure(reason: str, status_code: int, detail: str) -> RedirectResponse:
    """Fail a sign-in the way the caller's client can actually render.

    The web app drives this endpoint with fetch and shows its own message, so it
    keeps the JSON error it has always had. The desktop shell does not: the OAuth
    dance runs in the *system browser*, which renders whatever the loopback
    sidecar returns. A raised `HTTPException` there is a bare `{"detail": ...}`
    on a white page — and an unhandled exception is a bare "Internal Server
    Error" — landing the user somewhere with no way back, after they have
    already approved at Google. So on the desktop, hand off to the relay page
    with a reason it can explain instead.

    `duct_local` is the right test: only the desktop sidecar runs local, and it
    only ever serves the desktop flow.
    """
    cfg = get_configs()
    if cfg.duct_local:
        return _no_store_redirect(f"{cfg.frontend_origin}/desktop-auth?error={reason}", 307)
    raise HTTPException(status_code=status_code, detail=detail)


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
    client: str = Query(default=""),
) -> RedirectResponse:
    """Start Google OAuth for user sign-in.

    ``client=desktop`` marks the flow as initiated from the desktop shell's
    system browser; the callback then routes the auth code back to the shell.
    """
    cfg = get_configs()
    if turnstile_token:
        client_ip = request.client.host if request.client else ""
        valid = await verify_turnstile(turnstile_token, client_ip)
        if not valid:
            raise HTTPException(status_code=403, detail="Turnstile verification failed.")
    elif cfg.turnstile_secret_key and not cfg.duct_local:
        # Turnstile is a widget on the hosted login page, which solves the
        # challenge and passes the token here. The desktop shell has no such
        # page — it opens the system browser directly at this endpoint — so it
        # can never produce a token, and requiring one blocks sign-in outright
        # the moment a sidecar is pointed at an env that configures Turnstile.
        # The sidecar binds loopback only, so there is no bot surface to defend.
        #
        # Gated on `duct_local` (server-side config), never on `client=desktop`:
        # that is a caller-supplied query parameter, so keying on it would let
        # anyone skip the challenge on the hosted API by appending it.
        raise HTTPException(status_code=400, detail="Turnstile token required.")

    state = secrets.token_urlsafe(32)
    try:
        flow = create_google_signin_flow(state=state)
    except ValueError as exc:
        logger.error("Google sign-in is not configured: %s", exc)
        return _signin_failure(SIGNIN_ERROR_CONFIG, 500, str(exc))

    auth_url, _ = flow.authorization_url(
        access_type="online",
        include_granted_scopes="false",
        prompt="select_account",
    )
    cleanup_expired_states()
    flow_name = SIGNIN_DESKTOP_FLOW if client == "desktop" else SIGNIN_FLOW
    save_state(state, flow.code_verifier, flow_name, OAUTH_STATE_TTL_SECONDS)
    return _no_store_redirect(auth_url, status_code=307)


@router.get("/auth/signin/google/callback")
def signin_google_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    """Google OAuth callback for user sign-in. Exchanges code, creates JWT, redirects to app.

    Nothing here is allowed to escape as an unhandled exception. By the time the
    browser arrives the user has already approved at Google, so a stack trace
    rendered as "Internal Server Error" strands them on a dead page with no way
    back and nothing to report. Every failure becomes a reason the relay page can
    explain — and, on the way out, a logged traceback.
    """
    try:
        return _signin_google_callback(code=code, state=state)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in the Google sign-in callback")
        return _signin_failure(SIGNIN_ERROR_SERVER, 500, "Sign-in failed.")


def _signin_google_callback(*, code: str, state: str) -> RedirectResponse:
    if not code or not state:
        return _signin_failure(SIGNIN_ERROR_EXPIRED, 400, "Missing OAuth code or state.")
    matched_flow, code_verifier = consume_state_for_flows(
        state, (SIGNIN_FLOW, SIGNIN_DESKTOP_FLOW), OAUTH_STATE_TTL_SECONDS
    )
    if matched_flow is None:
        return _signin_failure(SIGNIN_ERROR_EXPIRED, 400, "Invalid or expired OAuth state.")

    try:
        flow = create_google_signin_flow(state=state)
        if code_verifier is not None:
            flow.code_verifier = code_verifier
    except ValueError as exc:
        logger.error("Google sign-in is not configured: %s", exc)
        return _signin_failure(SIGNIN_ERROR_CONFIG, 500, str(exc))

    try:
        flow.fetch_token(code=code)
    except Exception:
        logger.exception("OAuth token exchange failed")
        return _signin_failure(SIGNIN_ERROR_EXCHANGE, 502, "OAuth token exchange failed.")

    creds = flow.credentials
    if not creds or not creds.id_token:
        logger.error("Google returned no ID token for the sign-in flow")
        return _signin_failure(SIGNIN_ERROR_IDENTITY, 502, "No ID token returned by Google.")

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
        except Exception:
            logger.exception("Failed to verify Google ID token")
            return _signin_failure(SIGNIN_ERROR_IDENTITY, 502, "Failed to verify ID token.")

    provider_user_id = id_info.get("sub", "")
    email = id_info.get("email", "")
    name = id_info.get("name", "")
    picture = id_info.get("picture", "")

    if not provider_user_id or not email:
        logger.error("Google ID token was missing sub/email")
        return _signin_failure(
            SIGNIN_ERROR_IDENTITY, 502, "Google ID token missing required identity fields."
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
    except ValueError:
        logger.exception("JWT creation failed")
        return _signin_failure(SIGNIN_ERROR_SERVER, 500, "Authentication error.")

    # C1 fix: deliver JWT via a short-lived exchange code so it never appears in
    # the URL query string (browser history, server logs, Referer headers).
    auth_code = store_exchange_code(token)
    cfg = get_configs()
    if matched_flow == SIGNIN_DESKTOP_FLOW:
        # Desktop flow runs in the system browser; the app's relay page fires
        # the ai.getduct.desktop:// deep link that returns the code to the
        # shell (HTML stays in the app — the backend only redirects).
        redirect_url = f"{cfg.frontend_origin}/desktop-auth?auth_code={auth_code}"
    else:
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
