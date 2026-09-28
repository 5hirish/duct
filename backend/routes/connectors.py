"""Connector-agnostic API (accounts, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from starlette.status import HTTP_404_NOT_FOUND, HTTP_501_NOT_IMPLEMENTED

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    get_connector,
    server_only_keys_in,
)

router = APIRouter(tags=["connectors"])


class ConnectorAccountsRequest(BaseModel):
    refresh_token: str = ""
    login_customer_id: str = ""  # MCC override
    # Manual-credential connectors (apple_ads, meta_ads, stripe, revenuecat,
    # openai_ads): arbitrary key/value credentials the adapter reads from
    # auth.extras (api_key, access_token, private_key, team_id, …).
    credentials: dict[str, str] = {}


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
    # The same refusal as saving: listing with a grant this caller did not
    # earn would read someone else's repository names.
    reserved = server_only_keys_in(connector_id, body.credentials)
    if reserved:
        raise HTTPException(
            status_code=422,
            detail=f"{', '.join(reserved)} is set by Duct's own connect flow, never by a request.",
        )

    extras = {
        key: value.strip()
        for key, value in (
            ("login_customer_id", body.login_customer_id),
        )
        if value.strip()
    }
    # Manual-credential connectors carry their whole credential shape here.
    extras.update({k: v.strip() for k, v in (body.credentials or {}).items() if v and v.strip()})
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
