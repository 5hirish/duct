"""Insight lifecycle routes (refreshing saved insight data)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from config import get_configs
from routes.schemas import InsightRefreshRequest, InsightRefreshResponse
from service.pipeline import (
    build_connector_brief,
    fetch_connector_payload,
    normalize_connections,
    now_iso,
    resolve_date_range,
)

router = APIRouter(tags=["insights"])


@router.post("/refresh", response_model=InsightRefreshResponse)
async def refresh_insight(req: InsightRefreshRequest) -> InsightRefreshResponse:
    connections = normalize_connections(req.connections)
    date_from, date_to = resolve_date_range(req.date_preset, req.date_from, req.date_to)
    cfg = get_configs()

    async def fetch_connector(connector_id: str) -> tuple[str, dict[str, Any]]:
        target = req.targets.get(connector_id)
        return connector_id, await fetch_connector_payload(
            connector_id=connector_id,
            date_from=date_from,
            date_to=date_to,
            cfg=cfg,
            refresh_token=req.refresh_token,
            developer_token=req.developer_token,
            ga4_refresh_token=req.ga4_refresh_token,
            gsc_refresh_token=req.gsc_refresh_token,
            customer_id=target.customer_id if target else "",
            account_name=target.account_name if target else "",
            currency_code=target.currency_code if target else "USD",
            login_customer_id=target.login_customer_id if target else "",
            ga4_property_id=target.property_id if target else "",
            gsc_site_url=target.site_url if target else "",
        )

    fetched_rows = await asyncio.gather(*(fetch_connector(c) for c in connections), return_exceptions=True)
    fetch_failures = [item for item in fetched_rows if isinstance(item, Exception)]
    if fetch_failures:
        detail = "; ".join(str(err) for err in fetch_failures)
        raise HTTPException(status_code=502, detail=detail)
    raw_by_connector = {connector_id: payload for connector_id, payload in fetched_rows}

    async def normalize_connector(connector_id: str, raw_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        brief = await asyncio.to_thread(
            build_connector_brief,
            connector_id=connector_id,
            raw_data=raw_data,
            date_from=date_from,
            date_to=date_to,
        )
        return connector_id, brief

    normalized_rows = await asyncio.gather(
        *(normalize_connector(connector_id, raw_data) for connector_id, raw_data in raw_by_connector.items()),
        return_exceptions=True,
    )
    normalize_failures = [item for item in normalized_rows if isinstance(item, Exception)]
    if normalize_failures:
        detail = "; ".join(str(err) for err in normalize_failures)
        raise HTTPException(status_code=500, detail=detail)
    briefs = {connector_id: payload for connector_id, payload in normalized_rows}

    return InsightRefreshResponse(
        refreshed_at=now_iso(),
        briefs=briefs,
        date_from=date_from,
        date_to=date_to,
    )
