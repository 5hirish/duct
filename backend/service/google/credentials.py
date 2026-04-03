"""Google Ads credential and artifact naming helpers (shared by API routes)."""

from __future__ import annotations

from fastapi import HTTPException

from config import get_configs


def resolve_ads_credentials(*, request_refresh_token: str | None) -> tuple[str, str, str, str]:
    """Resolve developer token, OAuth client, and refresh token from env + request."""
    cfg = get_configs()
    dt = cfg.google_ads_developer_token
    cid = cfg.google_oauth_client_id or cfg.google_ads_client_id
    secret = cfg.google_oauth_client_secret or cfg.google_ads_client_secret
    rt = (request_refresh_token or "").strip() or cfg.google_ads_refresh_token
    if not all([dt, cid, secret, rt]):
        raise HTTPException(
            status_code=422,
            detail=(
                "Missing Google Ads credentials. Set GOOGLE_ADS_DEVELOPER_TOKEN, "
                "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET and provide refresh_token."
            ),
        )
    return dt, cid, secret, rt


def resolve_customer_id(*, request_customer_id: str | None) -> str:
    """Customer ID from request body or server default."""
    cid = (request_customer_id or get_configs().google_ads_customer_id).strip()
    if not cid:
        raise HTTPException(status_code=422, detail="Missing customer_id.")
    return cid


def report_basename(customer_stripped: str, date_to: str, *, demo: bool) -> str:
    """Filename for a persisted report JSON under ``reports/``."""
    if demo:
        return f"demo-{date_to}.json"
    return f"{customer_stripped}-{date_to}.json"
