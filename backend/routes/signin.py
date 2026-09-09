"""User sign-in via Google OAuth (identity, not data-source access)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from config import get_configs
from models.auth import User
from service.auth import get_current_user
from service.auth_exchange import (
    consume_exchange_code,
    consume_link_code,
    store_exchange_code,
    store_link_code,
)
from service.connector_scopes import join_scopes, parse_scopes
from service.google.oauth import create_google_signin_flow, signin_scopes
from service.oauthstate import (
    cleanup_expired_states,
    consume_state_full,
    save_state,
)
from service.ratelimit import RateLimit
from service.signin_sources import bundle_scopes, is_bundle, store_granted_sources
from service.turnstile import verify_turnstile
from service.user_store import get_or_create_guest, is_guest_user, upsert_google_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signin"])

OAUTH_STATE_TTL_SECONDS = 300
SIGNIN_FLOW = "signin_google"
# Same sign-in flow initiated from the desktop shell: the OAuth dance runs in
# the user's browser, so the callback must hand the auth code back to the shell
# (via the app's /desktop-auth relay page) instead of the web login page. The
# distinct flow name rides in the existing state store — no schema change.
SIGNIN_DESKTOP_FLOW = "signin_google_desktop"
# The onboarding bundle: the same sign-in, asking for the Search Console and
# Analytics read scopes in the same consent (`service/signin_sources.py`). Its
# own flow names because the callback has to rebuild the flow with the same
# scopes and then store what was granted — and because the base flows must
# stay identity-only, which a flag on them would make easy to forget.
SIGNIN_SOURCES_FLOW = "signin_google_sources"
SIGNIN_SOURCES_DESKTOP_FLOW = "signin_google_sources_desktop"
SIGNIN_FLOWS = (
    SIGNIN_FLOW, SIGNIN_DESKTOP_FLOW, SIGNIN_SOURCES_FLOW, SIGNIN_SOURCES_DESKTOP_FLOW,
)
_DESKTOP_FLOWS = frozenset({SIGNIN_DESKTOP_FLOW, SIGNIN_SOURCES_DESKTOP_FLOW})
_SOURCES_FLOWS = frozenset({SIGNIN_SOURCES_FLOW, SIGNIN_SOURCES_DESKTOP_FLOW})

JWT_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days
# "Keep me signed in" on the login page. A plain JWT-in-localStorage design
# has no revoke, so this is a duration choice, not a security boundary — the
# token is exactly as bearer-valid for 30 days as the 7-day one is for 7.
REMEMBER_JWT_EXPIRY_SECONDS = 30 * 24 * 60 * 60  # 30 days


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


def _create_jwt(
    email: str,
    name: str,
    picture: str,
    *,
    new_user: bool = False,
    uid: str = "",
    guest: bool = False,
    remember: bool = False,
) -> str:
    cfg = get_configs()
    if not cfg.jwt_secret:
        raise ValueError("JWT_SECRET is not configured.")
    now = datetime.now(timezone.utc)
    expiry_seconds = REMEMBER_JWT_EXPIRY_SECONDS if remember else JWT_EXPIRY_SECONDS
    payload = {
        "sub": email,
        "name": name,
        "picture": picture,
        # True only on the sign-in that created the account, so the app can tell
        # a signup from a login. The claim rides a token that lives for a week,
        # so the app must fire on receiving it, never on decoding it.
        "new_user": new_user,
        # The user row's UUID. `sub` is the email and analytics must never
        # receive that; this is what identifies someone to GA4, so the same
        # person on the desktop app and in a browser counts once.
        "uid": uid,
        # A guest holds a real token for a real row; the claim is what lets the
        # app show "save your work" instead of an account it never asked for.
        "guest": guest,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + expiry_seconds,
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Guests — an account before a sign-in
# ---------------------------------------------------------------------------

# Per source address. One install mints one guest, so a legitimate client
# never comes near this; a script minting rows does within a second.
_GUEST_LIMIT = RateLimit(limit=20, window_seconds=60.0)


class GuestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Desktop: stable per install, from the shell. Web: a uuid the page
    # generates once and keeps in storage. Validated in the store.
    install_id: str


@router.post("/auth/guest")
def create_guest(body: GuestRequest, request: Request) -> dict:
    """A token for someone who has not signed in.

    Idempotent on ``install_id``, so relaunching resumes the same guest and
    the project they drafted is still theirs. See ``service/user_store.py``
    for why a guest is a real user row rather than a nullable owner.
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = _GUEST_LIMIT.allow(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many new sessions from this address. Try again in a minute.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    try:
        guest = get_or_create_guest(body.install_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        token = _create_jwt(guest.email, "Guest", "", new_user=guest.created, uid=guest.user_id, guest=True)
    except ValueError:
        logger.exception("JWT creation failed for a guest")
        raise HTTPException(status_code=500, detail="Authentication error.") from None
    return {"token": token, "created": guest.created}


@router.post("/auth/guest/link-code")
def create_guest_link_code(user: User = Depends(get_current_user)) -> dict:
    """A five-minute code naming this guest, for the sign-in authorize URL.

    The authorize endpoint is a browser navigation and carries no bearer
    token, so this is how a guest says "link the account you are about to
    create to me" without putting its JWT in a URL.
    """
    if not is_guest_user(user):
        raise HTTPException(status_code=409, detail="This account is already signed in.")
    return {"code": store_link_code(str(user.id))}


def _signin_scopes(bundled: bool) -> list[str] | None:
    """The identity scopes, plus the bundle's read scopes when asked for.

    ``None`` keeps the flow builder's own default for the plain sign-in, so
    that path is byte-for-byte what it was before the bundle existed.
    """
    if not bundled:
        return None
    return [*signin_scopes(), *bundle_scopes()]


def _flow_name(*, desktop: bool, bundled: bool) -> str:
    if bundled:
        return SIGNIN_SOURCES_DESKTOP_FLOW if desktop else SIGNIN_SOURCES_FLOW
    return SIGNIN_DESKTOP_FLOW if desktop else SIGNIN_FLOW


def _store_signin_sources(flow, *, user_id: str) -> list[str]:
    """Store the bundle's grant for ``user_id``; empty when nothing was granted
    or nothing could be read. Never raises — the sign-in already succeeded."""
    try:
        granted = join_scopes(parse_scopes(flow.oauth2session.token.get("scope")))
    except Exception:  # noqa: BLE001 — an unreadable grant stores nothing
        logger.warning("sign-in bundle: could not read granted scopes", exc_info=True)
        return []
    refresh_token = (getattr(flow.credentials, "refresh_token", "") or "").strip()
    if not refresh_token:
        logger.info("sign-in bundle: Google returned no refresh token; nothing stored")
        return []
    return store_granted_sources(user_id, refresh_token=refresh_token, granted_scopes=granted)


@router.get("/auth/signin/google/authorize")
async def signin_google_authorize(
    request: Request,
    turnstile_token: str = Query(default=""),
    client: str = Query(default=""),
    link: str = Query(default=""),
    sources: str = Query(default=""),
    remember: str = Query(default=""),
) -> RedirectResponse:
    """Start Google OAuth for user sign-in.

    ``client=desktop`` marks the flow as initiated from the desktop shell's
    system browser; the callback then routes the auth code back to the shell.

    ``sources=onboarding`` asks for the onboarding bundle — Search Console and
    Analytics read scopes in the same consent — and is honoured only by that
    name. It is set by one surface: the connector prompt on the onboarding
    audit, for a guest. Every other sign-in stays identity-only, and the
    Connections page keeps asking for each connector's own scopes. Caller-
    supplied, and safe to be: it can only add consent boxes the user sees and
    may untick, never skip a check or widen what is stored beyond the grant.

    ``link`` is a code from ``/auth/guest/link-code``: the guest whose work
    the resulting account should own. Redeemed here, before Google, and the
    resolved id rides the OAuth state to the callback. An invalid or expired
    code is ignored rather than refused — the sign-in still works, it simply
    does not link, and the app says so.

    ``remember`` is the login page's "keep me signed in" box, any non-empty
    value counting as ticked. It rides the OAuth state the same way ``link``
    does and picks the JWT's lifetime at the callback.
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
    bundled = is_bundle(sources)
    if sources and not bundled:
        logger.info("sign-in asked for unknown source bundle %r; proceeding identity-only", sources)
    try:
        flow = create_google_signin_flow(state=state, scopes=_signin_scopes(bundled))
    except ValueError as exc:
        logger.error("Google sign-in is not configured: %s", exc)
        return _signin_failure(SIGNIN_ERROR_CONFIG, 500, str(exc))

    if bundled:
        # A data scope is only useful with a refresh token, which Google
        # issues on an offline grant and — for an account that has approved
        # Duct before — only when consent is shown again.
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="false",
            prompt="consent select_account",
        )
    else:
        auth_url, _ = flow.authorization_url(
            access_type="online",
            include_granted_scopes="false",
            prompt="select_account",
        )
    cleanup_expired_states()
    flow_name = _flow_name(desktop=client == "desktop", bundled=bundled)
    link_user_id = consume_link_code(link) if link else None
    if link and link_user_id is None:
        logger.info("sign-in started with a stale guest link code; proceeding unlinked")
    save_state(
        state,
        flow.code_verifier,
        flow_name,
        OAUTH_STATE_TTL_SECONDS,
        link_user_id=link_user_id,
        remember=bool(remember),
    )
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
    matched_flow, code_verifier, link_user_id, remember = consume_state_full(
        state, SIGNIN_FLOWS, OAUTH_STATE_TTL_SECONDS
    )
    if matched_flow is None:
        return _signin_failure(SIGNIN_ERROR_EXPIRED, 400, "Invalid or expired OAuth state.")
    bundled = matched_flow in _SOURCES_FLOWS

    try:
        flow = create_google_signin_flow(state=state, scopes=_signin_scopes(bundled))
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

    upserted = upsert_google_user(
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
        link_user_id=link_user_id,
    )

    try:
        token = _create_jwt(
            normalized_email,
            name,
            picture,
            new_user=upserted.created,
            uid=upserted.user_id,
            remember=remember,
        )
    except ValueError:
        logger.exception("JWT creation failed")
        return _signin_failure(SIGNIN_ERROR_SERVER, 500, "Authentication error.")

    if bundled:
        # After the account exists, never before: the rows need an owner. What
        # is stored is what Google says was granted, read off the token
        # response (`flow.credentials.granted_scopes` is never populated by
        # the installed google-auth-oauthlib). Declining every box is a
        # complete sign-in with nothing stored, not a failure.
        _store_signin_sources(flow, user_id=upserted.user_id)

    # C1 fix: deliver JWT via a short-lived exchange code so it never appears in
    # the URL query string (browser history, server logs, Referer headers).
    auth_code = store_exchange_code(token)
    cfg = get_configs()
    if matched_flow in _DESKTOP_FLOWS:
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
