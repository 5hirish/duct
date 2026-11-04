"""Connector-agnostic API: verifying pasted keys by the accounts they reach."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
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
    # Manual-credential connectors (apple_ads, meta_ads, stripe, revenuecat,
    # openai_ads, …): the keys being pasted, verified by listing what they
    # reach before they are saved. The adapter reads them from auth.extras.
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
    # A sign-in connector's credential lives only on the server, so there is
    # nothing a request could verify here: its accounts come from the stored
    # row (`GET /api/user/connectors/{id}/entities`).
    if meta.oauth_scope:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{meta.label} is connected by signing in, not with pasted keys. "
                "Its accounts are listed from the stored connection."
            ),
        )
    # The same refusal as saving: listing with a grant this caller did not
    # earn would read someone else's repository names.
    reserved = server_only_keys_in(connector_id, body.credentials)
    if reserved:
        raise HTTPException(
            status_code=422,
            detail=f"{', '.join(reserved)} is set by Duct's own connect flow, never by a request.",
        )

    extras = {k: v.strip() for k, v in (body.credentials or {}).items() if v and v.strip()}
    auth = ConnectorAuthContext(connector_id=connector_id, extras=extras)
    try:
        accounts = adapter.list_accounts(auth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"accounts": accounts}


@router.post("/{connector_id}/accounts")
def list_connector_accounts(connector_id: str, body: ConnectorAccountsRequest) -> dict:
    """Verify pasted keys by listing the accounts they reach.

    The GET variant, which took a refresh token in the query string, is gone
    with the last client that held a token to send.
    """
    return _list_accounts(connector_id, body)
