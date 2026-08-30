"""OAuth entrypoints keyed by connector_id (browser flow; no API key on these routes)."""

from __future__ import annotations

import logging
import secrets
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_501_NOT_IMPLEMENTED

from config import get_configs
from service.auth_exchange import consume_connector_code, store_connector_code
from service.connectors import get_connector, normalize_connector_id
from service.google.constants import (
    GA4_CONNECTOR_ID,
    GOOGLE_ADS_CONNECTOR_ID,
    GSC_CONNECTOR_ID,
    GTM_CONNECTOR_ID,
)
from service.google.oauth import create_google_oauth_flow
from service.oauthstate import (
    cleanup_expired_states,
    consume_state_for_flows,
    save_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

OAUTH_STATE_TTL_SECONDS = 300

# Flow names stored alongside the OAuth state. Each has a `_desktop` twin
# marking a connect started from the desktop shell's *system browser* — the same
# OAuth dance, but a different way home (see `_connector_success`). Riding in
# the existing `flow` column means no schema change, the same trick
# `signin.py` plays with SIGNIN_DESKTOP_FLOW.
DESKTOP_FLOW_SUFFIX = "_desktop"
CONNECTOR_FLOW_GOOGLE_ADS = "connector_google_ads"
CONNECTOR_FLOW_GA4 = "connector_ga4"
CONNECTOR_FLOW_GSC = "connector_gsc"
CONNECTOR_FLOW_GTM = "connector_gtm"

# base flow -> (connector id, URL-fragment key the web app reads the token from)
FLOW_TO_CALLBACK = {
    CONNECTOR_FLOW_GOOGLE_ADS: (GOOGLE_ADS_CONNECTOR_ID, "refresh_token"),
    CONNECTOR_FLOW_GA4: (GA4_CONNECTOR_ID, "ga4_refresh_token"),
    CONNECTOR_FLOW_GSC: (GSC_CONNECTOR_ID, "gsc_refresh_token"),
    CONNECTOR_FLOW_GTM: (GTM_CONNECTOR_ID, "gtm_refresh_token"),
}
CONNECTOR_TO_FLOW = {connector_id: flow for flow, (connector_id, _) in FLOW_TO_CALLBACK.items()}
# Every flow the shared /auth/google/callback accepts, desktop twins included.
GOOGLE_CONNECTOR_FLOWS = tuple(
    flow for base in FLOW_TO_CALLBACK for flow in (base, base + DESKTOP_FLOW_SUFFIX)
)

# Reason codes the /desktop-auth relay page knows how to explain. Deliberately
# coarse and non-identifying: they end up in a URL the user can see and paste.
CONNECT_ERROR_EXPIRED = "expired"
CONNECT_ERROR_EXCHANGE = "exchange"
CONNECT_ERROR_CONSENT = "consent"
CONNECT_ERROR_CONFIG = "config"
CONNECT_ERROR_UNKNOWN = "unknown"
CONNECT_ERROR_SERVER = "server"


def _no_store_redirect(url: str, status_code: int = 307) -> RedirectResponse:
    """Build a redirect response that disables client/proxy caching."""
    response = RedirectResponse(url=url, status_code=status_code)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _split_flow(flow: str) -> tuple[str, bool]:
    """Split a stored flow name into its base name and "was this the desktop shell?"."""
    if flow.endswith(DESKTOP_FLOW_SUFFIX):
        return flow[: -len(DESKTOP_FLOW_SUFFIX)], True
    return flow, False


def _connector_failure(
    reason: str,
    status_code: int,
    detail: str,
    *,
    desktop: bool,
    connector_id: str = "",
) -> RedirectResponse:
    """Fail a connect the way the caller's client can actually render.

    In a browser the web app owns the whole flow and an `HTTPException` is fine
    — it never leaves the app's own tab. The desktop shell is the case this
    exists for: the OAuth dance runs in the *system browser*, which renders
    whatever the loopback sidecar returns, so a raised exception is a bare
    `{"detail": ...}` on a white page — and an unhandled one a bare "Internal
    Server Error" — stranding the user in a browser tab with no way back, after
    they have already approved at Google. Hand off to the relay page with a
    reason it can explain instead. Same problem, same answer, and the same page
    as `_signin_failure` in `routes/signin.py`.
    """
    if not desktop:
        raise HTTPException(status_code=status_code, detail=detail)
    cfg = get_configs()
    query = f"connector={quote(connector_id, safe='')}&error={quote(reason, safe='')}"
    return _no_store_redirect(f"{cfg.frontend_origin}/desktop-auth?{query}", 307)


def _connector_success(
    *,
    connector_id: str,
    token_fragment_key: str,
    refresh_token: str,
    desktop: bool,
) -> RedirectResponse:
    """Hand the refresh token back to whichever client started the flow.

    Browser: straight back to /connections with the token in the URL *fragment*,
    which browsers never send to a server and the page strips on arrival.

    Desktop: the flow ends in the system browser and has to cross back into the
    app through a custom-scheme deep link — a URL handled by whatever app claims
    the scheme, and visible to the browser besides. A connector refresh token is
    long-lived and must never ride in one, so it stays on the backend behind a
    single-use 60-second code, exactly as the sign-in JWT does.
    """
    cfg = get_configs()
    if desktop:
        code = store_connector_code(connector_type=connector_id, refresh_token=refresh_token)
        query = f"connector={quote(connector_id, safe='')}&auth_code={quote(code, safe='')}"
        return _no_store_redirect(f"{cfg.frontend_origin}/desktop-auth?{query}", 307)
    redirect_url = (
        f"{cfg.frontend_origin}/connections#{token_fragment_key}={quote(refresh_token, safe='')}"
    )
    return _no_store_redirect(redirect_url, status_code=307)


def _google_connector_authorize(connector_id: str, *, desktop: bool) -> RedirectResponse:
    flow_key = CONNECTOR_TO_FLOW[connector_id]
    if desktop:
        flow_key += DESKTOP_FLOW_SUFFIX
    state = secrets.token_urlsafe(32)
    try:
        meta, _ = get_connector(connector_id)
        scope = meta.oauth_scope
        if not scope:
            raise ValueError(f"Connector {connector_id!r} is missing oauth scope.")
        # oauth_scope may hold several space-separated scopes (e.g. GTM).
        flow = create_google_oauth_flow(state=state, scopes=scope.split())
    except KeyError:
        return _connector_failure(
            CONNECT_ERROR_UNKNOWN,
            HTTP_404_NOT_FOUND,
            "Unknown connector",
            desktop=desktop,
            connector_id=connector_id,
        )
    except ValueError as exc:
        logger.error("Connector OAuth is not configured: %s", exc)
        return _connector_failure(
            CONNECT_ERROR_CONFIG, 500, str(exc), desktop=desktop, connector_id=connector_id
        )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
    )
    cleanup_expired_states()
    save_state(state, flow.code_verifier, flow_key, OAUTH_STATE_TTL_SECONDS)
    return _no_store_redirect(auth_url, status_code=307)


def _google_connector_callback_with_state(
    *,
    connector_id: str,
    code: str,
    state: str,
    token_fragment_key: str,
    code_verifier: str | None,
    desktop: bool,
) -> RedirectResponse:
    try:
        meta, _ = get_connector(connector_id)
        scope = meta.oauth_scope
        if not scope:
            raise ValueError(f"Connector {connector_id!r} is missing oauth scope.")
        flow = create_google_oauth_flow(state=state, scopes=scope.split())
        if code_verifier is not None:
            flow.code_verifier = code_verifier
    except KeyError:
        return _connector_failure(
            CONNECT_ERROR_UNKNOWN,
            HTTP_404_NOT_FOUND,
            "Unknown connector",
            desktop=desktop,
            connector_id=connector_id,
        )
    except ValueError as exc:
        logger.error("Connector OAuth is not configured: %s", exc)
        return _connector_failure(
            CONNECT_ERROR_CONFIG, 500, str(exc), desktop=desktop, connector_id=connector_id
        )

    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # pragma: no cover - upstream oauth errors vary
        logger.exception("OAuth token exchange failed for connector %r", connector_id)
        return _connector_failure(
            CONNECT_ERROR_EXCHANGE,
            502,
            f"OAuth token exchange failed: {exc}",
            desktop=desktop,
            connector_id=connector_id,
        )

    refresh_token = (flow.credentials.refresh_token or "").strip()
    if not refresh_token:
        return _connector_failure(
            CONNECT_ERROR_CONSENT,
            502,
            "No refresh token returned by Google. Re-consent is required.",
            desktop=desktop,
            connector_id=connector_id,
        )

    return _connector_success(
        connector_id=connector_id,
        token_fragment_key=token_fragment_key,
        refresh_token=refresh_token,
        desktop=desktop,
    )


def _google_connector_callback(*, connector_id: str, code: str, state: str) -> RedirectResponse:
    """Per-connector callback: accepts this connector's browser or desktop flow."""
    base_flow = CONNECTOR_TO_FLOW[connector_id]
    _, token_fragment_key = FLOW_TO_CALLBACK[base_flow]
    # Before the state is consumed there is nothing to say which client started
    # the flow, so fall back on where this process runs: only the desktop
    # sidecar runs local. Same test, same reason, as `_signin_failure`.
    assumed_desktop = get_configs().duct_local

    if not code:
        return _connector_failure(
            CONNECT_ERROR_EXPIRED,
            400,
            "Missing OAuth code.",
            desktop=assumed_desktop,
            connector_id=connector_id,
        )
    if not state:
        return _connector_failure(
            CONNECT_ERROR_EXPIRED,
            400,
            "Invalid or expired OAuth state.",
            desktop=assumed_desktop,
            connector_id=connector_id,
        )
    matched_flow, code_verifier = consume_state_for_flows(
        state, (base_flow, base_flow + DESKTOP_FLOW_SUFFIX), OAUTH_STATE_TTL_SECONDS
    )
    if matched_flow is None:
        return _connector_failure(
            CONNECT_ERROR_EXPIRED,
            400,
            "Invalid or expired OAuth state.",
            desktop=assumed_desktop,
            connector_id=connector_id,
        )
    _, desktop = _split_flow(matched_flow)
    return _google_connector_callback_with_state(
        connector_id=connector_id,
        code=code,
        state=state,
        token_fragment_key=token_fragment_key,
        code_verifier=code_verifier,
        desktop=desktop,
    )


@router.get("/auth/connectors/{connector_id}/oauth/authorize")
def connector_oauth_authorize(
    connector_id: str,
    client: str = Query(default=""),
) -> RedirectResponse:
    """Start OAuth for a connector that supports it (e.g. ``google_ads``).

    ``client=desktop`` marks a connect started from the desktop shell, which
    runs the dance in the system browser because Google refuses OAuth inside an
    embedded webview. The callback then returns the credentials through the
    shell's deep link instead of redirecting a browser tab that is not the app.

    Unlike `signin.py`'s Turnstile gate, keying on this caller-supplied value is
    safe: it decides only where a user's *own* freshly granted token is handed
    back to, never what is granted or who is trusted.
    """
    cid = normalize_connector_id(connector_id)
    try:
        meta, _ = get_connector(cid)
    except KeyError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Unknown connector",
        ) from exc

    if cid in CONNECTOR_TO_FLOW:
        return _google_connector_authorize(cid, desktop=client == "desktop")

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

    if cid not in CONNECTOR_TO_FLOW:
        raise HTTPException(
            status_code=HTTP_501_NOT_IMPLEMENTED,
            detail=f"Connector {cid!r} does not support OAuth yet.",
        )
    try:
        return _google_connector_callback(connector_id=cid, code=code, state=state)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in the %s OAuth callback", cid)
        return _connector_failure(
            CONNECT_ERROR_SERVER,
            500,
            "Connecting failed.",
            desktop=get_configs().duct_local,
            connector_id=cid,
        )


@router.get("/auth/google/callback")
def google_oauth_callback_short_path(
    code: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    """Shared callback that routes GA4/GSC/GTM/Google Ads by stored OAuth flow state.

    Nothing here is allowed to escape as an unhandled exception. By the time the
    browser arrives the user has already approved at Google, so a stack trace
    rendered as "Internal Server Error" strands them on a dead page with no way
    back and nothing to report — and on the desktop that page is a browser tab
    outside the app entirely.
    """
    try:
        return _google_oauth_callback_short_path(code=code, state=state)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in the connector OAuth callback")
        return _connector_failure(
            CONNECT_ERROR_SERVER, 500, "Connecting failed.", desktop=get_configs().duct_local
        )


def _google_oauth_callback_short_path(*, code: str, state: str) -> RedirectResponse:
    assumed_desktop = get_configs().duct_local
    if not code:
        return _connector_failure(
            CONNECT_ERROR_EXPIRED, 400, "Missing OAuth code.", desktop=assumed_desktop
        )
    if not state:
        return _connector_failure(
            CONNECT_ERROR_EXPIRED, 400, "Invalid or expired OAuth state.", desktop=assumed_desktop
        )
    matched_flow, code_verifier = consume_state_for_flows(
        state, GOOGLE_CONNECTOR_FLOWS, OAUTH_STATE_TTL_SECONDS
    )
    if matched_flow is None:
        return _connector_failure(
            CONNECT_ERROR_EXPIRED, 400, "Invalid or expired OAuth state.", desktop=assumed_desktop
        )
    base_flow, desktop = _split_flow(matched_flow)
    connector_id, token_fragment_key = FLOW_TO_CALLBACK[base_flow]
    return _google_connector_callback_with_state(
        connector_id=connector_id,
        code=code,
        state=state,
        token_fragment_key=token_fragment_key,
        code_verifier=code_verifier,
        desktop=desktop,
    )


@router.get("/auth/connectors/exchange")
def exchange_connector_code(code: str = Query(default="")) -> dict:
    """Single-use endpoint: exchange a 60-second code for connector credentials.

    The desktop shell's webview calls this once the deep link lands, mirroring
    `/auth/exchange` for sign-in. No API key and no session, for the same reason
    that one has none: the code *is* the credential — unguessable, single-use,
    and dead within a minute.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing auth code.")
    payload = consume_connector_code(code)
    if payload is None:
        raise HTTPException(status_code=400, detail="Invalid or expired auth code.")
    return payload
