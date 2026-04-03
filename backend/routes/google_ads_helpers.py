"""Shared Google Ads credential and path helpers for route handlers."""

from __future__ import annotations

from fastapi import HTTPException

from config import get_configs

from routes.schemas import ReportRequest


def resolve_ads_credentials(req: ReportRequest) -> tuple[str, str, str, str]:
    cfg = get_configs()
    dt = cfg.google_ads_developer_token
    cid = cfg.google_oauth_client_id or cfg.google_ads_client_id
    secret = cfg.google_oauth_client_secret or cfg.google_ads_client_secret
    rt = req.refresh_token or cfg.google_ads_refresh_token
    if not all([dt, cid, secret, rt]):
        raise HTTPException(
            status_code=422,
            detail=(
                "Missing Google Ads credentials. Set GOOGLE_ADS_DEVELOPER_TOKEN, "
                "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET and provide refresh_token."
            ),
        )
    return dt, cid, secret, rt


def resolve_customer_id(req: ReportRequest) -> str:
    cid = (req.customer_id or get_configs().google_ads_customer_id).strip()
    if not cid:
        raise HTTPException(status_code=422, detail="Missing customer_id.")
    return cid


def report_basename(customer_stripped: str, date_to: str, *, demo: bool) -> str:
    if demo:
        return f"demo-{date_to}.json"
    return f"{customer_stripped}-{date_to}.json"
