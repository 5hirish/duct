"""Shared non-LLM pipeline helpers for report fetch and normalization."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from config import Configs
from service.google.brief import build_brief
from service.google.credentials import resolve_ads_credentials, resolve_customer_id
from service.google.fetch import fetch_campaigns
from service.google.ga4 import fetch_ga4_conversion_paths, fetch_ga4_landing_pages
from service.google.gsc import fetch_gsc_page_performance, fetch_gsc_query_performance

SUPPORTED_CONNECTORS = {"google_ads", "ga4", "gsc"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_connections(connections: list[str]) -> list[str]:
    if not connections:
        raise HTTPException(status_code=422, detail="At least one connection is required.")
    normalized = sorted({c.strip().lower().replace("-", "_") for c in connections if c.strip()})
    unsupported = sorted(set(normalized) - SUPPORTED_CONNECTORS)
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported connections: {', '.join(unsupported)}")
    return normalized


def resolve_ga_credentials(cfg: Configs) -> tuple[str, str]:
    client_id = (cfg.google_oauth_client_id or cfg.google_ads_client_id).strip()
    client_secret = (cfg.google_oauth_client_secret or cfg.google_ads_client_secret).strip()
    return client_id, client_secret


def resolve_date_range(preset: str, custom_from: str, custom_to: str) -> tuple[str, str]:
    if preset == "custom":
        if not custom_from or not custom_to:
            raise HTTPException(status_code=422, detail="date_from and date_to are required for custom date range.")
        return custom_from, custom_to
    days = {"7": 7, "30": 30, "90": 90}.get(preset, 30)
    today = date.today()
    return str(today - timedelta(days=days)), str(today)


async def fetch_connector_payload(
    *,
    connector_id: str,
    date_from: str,
    date_to: str,
    cfg: Configs,
    refresh_token: str = "",
    customer_id: str = "",
    account_name: str = "",
    currency_code: str = "USD",
    login_customer_id: str = "",
    ga4_property_id: str = "",
    gsc_site_url: str = "",
    ga4_refresh_token: str = "",
    gsc_refresh_token: str = "",
) -> dict[str, Any]:
    if connector_id == "google_ads":
        resolved_customer_id = resolve_customer_id(request_customer_id=customer_id)
        dt, cid, secret, rt = resolve_ads_credentials(request_refresh_token=refresh_token)
        data = await asyncio.to_thread(
            fetch_campaigns,
            customer_id=resolved_customer_id,
            developer_token=dt,
            client_id=cid,
            client_secret=secret,
            refresh_token=rt,
            date_from=date_from,
            date_to=date_to,
            account_name=account_name,
            currency_code=currency_code,
            login_customer_id=login_customer_id,
        )
        if not data.get("rows"):
            raise RuntimeError("No campaigns returned for this customer and date range.")
        return data

    ga_client_id, ga_client_secret = resolve_ga_credentials(cfg)
    if connector_id == "ga4":
        token = (ga4_refresh_token or refresh_token).strip()
        if not ga4_property_id:
            raise HTTPException(status_code=422, detail="ga4_property_id is required when GA4 is selected.")
        if not token:
            raise HTTPException(status_code=422, detail="ga4_refresh_token is required when GA4 is selected.")
        if not ga_client_id or not ga_client_secret:
            raise HTTPException(
                status_code=422,
                detail="Google OAuth client credentials are required for GA4/GSC connectors.",
            )
        landing_task = asyncio.to_thread(
            fetch_ga4_landing_pages,
            property_id=ga4_property_id,
            date_from=date_from,
            date_to=date_to,
            refresh_token=token,
            client_id=ga_client_id,
            client_secret=ga_client_secret,
        )
        paths_task = asyncio.to_thread(
            fetch_ga4_conversion_paths,
            property_id=ga4_property_id,
            date_from=date_from,
            date_to=date_to,
            refresh_token=token,
            client_id=ga_client_id,
            client_secret=ga_client_secret,
        )
        landing_pages, conversion_paths = await asyncio.gather(landing_task, paths_task)
        return {"landing_pages": landing_pages, "conversion_paths": conversion_paths}

    if connector_id == "gsc":
        token = (gsc_refresh_token or refresh_token).strip()
        if not gsc_site_url:
            raise HTTPException(status_code=422, detail="gsc_site_url is required when GSC is selected.")
        if not token:
            raise HTTPException(status_code=422, detail="gsc_refresh_token is required when GSC is selected.")
        if not ga_client_id or not ga_client_secret:
            raise HTTPException(
                status_code=422,
                detail="Google OAuth client credentials are required for GA4/GSC connectors.",
            )
        queries_task = asyncio.to_thread(
            fetch_gsc_query_performance,
            site_url=gsc_site_url,
            date_from=date_from,
            date_to=date_to,
            refresh_token=token,
            client_id=ga_client_id,
            client_secret=ga_client_secret,
        )
        pages_task = asyncio.to_thread(
            fetch_gsc_page_performance,
            site_url=gsc_site_url,
            date_from=date_from,
            date_to=date_to,
            refresh_token=token,
            client_id=ga_client_id,
            client_secret=ga_client_secret,
        )
        query_perf, page_perf = await asyncio.gather(queries_task, pages_task)
        return {"query_performance": query_perf, "page_performance": page_perf}

    raise RuntimeError(f"Unsupported connector: {connector_id}")


def build_connector_brief(*, connector_id: str, raw_data: dict[str, Any], date_from: str, date_to: str) -> dict[str, Any]:
    if connector_id == "google_ads":
        brief = build_brief(raw_data, theme="paid_ads")
        return brief.to_dict()

    theme = "product_intelligence" if connector_id == "ga4" else "organic_growth"
    return {
        "source_metadata": {
            "source": connector_id,
            "generated_at": now_iso(),
            "window_current": f"{date_from} to {date_to}",
            "theme": theme,
        },
        "summary": {
            "connector": connector_id,
            "datasets": list(raw_data.keys()),
        },
        "data": raw_data,
    }
