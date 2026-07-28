"""Connector-agnostic API (accounts, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from starlette.status import HTTP_404_NOT_FOUND, HTTP_501_NOT_IMPLEMENTED

from service.connectors import CAP_ACCOUNTS, ConnectorAuthContext, get_connector

router = APIRouter(tags=["connectors"])


class ConnectorAccountsRequest(BaseModel):
    refresh_token: str = ""
    developer_token: str = ""  # BYO Google Ads API access
    login_customer_id: str = ""  # MCC override


def _list_accounts(connector_id: str, body: ConnectorAccountsRequest) -> dict:
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

    extras = {
        key: value.strip()
        for key, value in (
            ("developer_token", body.developer_token),
            ("login_customer_id", body.login_customer_id),
        )
        if value.strip()
    }
    auth = ConnectorAuthContext(
        connector_id=connector_id,
        refresh_token=body.refresh_token.strip() or None,
        extras=extras,
    )
    try:
        accounts = adapter.list_accounts(auth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"accounts": accounts}


@router.post("/{connector_id}/accounts")
def list_connector_accounts_post(connector_id: str, body: ConnectorAccountsRequest) -> dict:
    """Preferred variant: credentials travel in the body, not the query string."""
    return _list_accounts(connector_id, body)


@router.get("/{connector_id}/accounts")
def list_connector_accounts(
    connector_id: str,
    refresh_token: str = Query(default=""),
) -> dict:
    return _list_accounts(connector_id, ConnectorAccountsRequest(refresh_token=refresh_token))
