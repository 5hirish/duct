"""Connector-agnostic API (accounts, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from starlette.status import HTTP_404_NOT_FOUND, HTTP_501_NOT_IMPLEMENTED

from service.connectors import CAP_ACCOUNTS, ConnectorAuthContext, get_connector

router = APIRouter(tags=["connectors"])


@router.get("/{connector_id}/accounts")
def list_connector_accounts(
    connector_id: str,
    refresh_token: str = Query(default=""),
) -> dict:
    try:
        meta, adapter = get_connector(connector_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Unknown connector",
        ) from exc

    if CAP_ACCOUNTS not in meta.capabilities:
        raise HTTPException(
            status_code=HTTP_501_NOT_IMPLEMENTED,
            detail=f"Connector {connector_id!r} does not support listing accounts.",
        )

    auth = ConnectorAuthContext(
        connector_id=connector_id,
        refresh_token=refresh_token.strip() or None,
    )
    try:
        accounts = adapter.list_accounts(auth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"accounts": accounts}
