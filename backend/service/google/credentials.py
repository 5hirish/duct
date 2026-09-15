"""Google Ads credential resolution for API routes (shared by generate + connectors)."""

from __future__ import annotations

from fastapi import HTTPException

from config import get_configs


def resolve_ads_credentials(
    *,
    request_refresh_token: str | None,
) -> tuple[str, str, str]:
    """Resolve the OAuth client and refresh token for a Google Ads call.

    No developer token is involved: Google sunset them on 2026-09-09, and the
    access level of a call is now that of the Cloud project owning
    ``GOOGLE_OAUTH_CLIENT_ID``. Credentials that resolve fine here can still
    come back empty against a production account if that project sits on Test
    access.
    """
    cfg = get_configs()
    cid = cfg.google_oauth_client_id or cfg.google_ads_client_id
    secret = cfg.google_oauth_client_secret or cfg.google_ads_client_secret
    rt = (request_refresh_token or "").strip() or cfg.google_ads_refresh_token
    if not all([cid, secret, rt]):
        raise HTTPException(
            status_code=422,
            detail=(
                "Missing Google Ads credentials. Set GOOGLE_OAUTH_CLIENT_ID and "
                "GOOGLE_OAUTH_CLIENT_SECRET, and connect Google Ads to provide a "
                "refresh_token."
            ),
        )
    return cid, secret, rt


def resolve_customer_id(*, request_customer_id: str | None) -> str:
    """Customer ID from request body or server default."""
    cid = (request_customer_id or get_configs().google_ads_customer_id).strip()
    if not cid:
        raise HTTPException(status_code=422, detail="Missing customer_id.")
    return cid
