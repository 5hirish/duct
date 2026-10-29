"""Insight lifecycle routes (refreshing saved insight data)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from config import get_configs
from db.session import get_session
from models.auth import User
from routes.schemas import InsightRefreshRequest, InsightRefreshResponse, RefreshRoutineTarget
from service.auth import get_current_user
from service.connector_access import resolve_read_credentials
from service.google.constants import GA4_CONNECTOR_ID, GSC_CONNECTOR_ID
from service.pipeline import (
    build_connector_brief,
    fetch_connector_payload,
    normalize_connections,
    resolve_date_range,
)
from utils.dates import now_iso

router = APIRouter(tags=["insights"])


def _target_account(connector_id: str, target: RefreshRoutineTarget | None) -> str:
    """The account a routine names for one connector, as its stored row keys it."""
    if target is None:
        return ""
    if connector_id == GA4_CONNECTOR_ID:
        return target.property_id
    if connector_id == GSC_CONNECTOR_ID:
        return target.site_url
    return target.customer_id


def _stored_credentials(
    session: Session, user_id: UUID, connections: list[str], targets: dict[str, RefreshRoutineTarget]
) -> dict[str, dict[str, str]]:
    """Each connector's credentials from the caller's own rows.

    No project id is taken, so no binding applies and no membership check is
    owed: a routine saved in this browser reads with its owner's connections,
    exactly as the request-body tokens it replaces did, minus the tab.
    """
    return {
        connector_id: resolve_read_credentials(
            session,
            user_id=user_id,
            connector_type=connector_id,
            account_id=_target_account(connector_id, targets.get(connector_id)),
        )
        for connector_id in connections
    }


@router.post("/refresh", response_model=InsightRefreshResponse)
async def refresh_insight(
    req: InsightRefreshRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> InsightRefreshResponse:
    connections = normalize_connections(req.connections)
    date_from, date_to = resolve_date_range(req.date_preset, req.date_from, req.date_to)
    cfg = get_configs()
    credentials = _stored_credentials(session, user.id, connections, req.targets)

    async def fetch_connector(connector_id: str) -> tuple[str, dict[str, Any]]:
        target = req.targets.get(connector_id)
        return connector_id, await fetch_connector_payload(
            connector_id=connector_id,
            date_from=date_from,
            date_to=date_to,
            cfg=cfg,
            credentials=credentials[connector_id],
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
