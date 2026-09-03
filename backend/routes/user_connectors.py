"""Connector credential endpoints — GET/POST/DELETE /api/user/connectors."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

from db.session import get_session
from models.auth import User
from models.connector import ConnectorCredential
from service.auth import get_current_user
from service.connector_access import list_data_sources
from service.connector_scopes import (
    SCOPE_NA,
    join_scopes,
    missing_scopes,
    parse_scopes,
    scope_rows,
    scope_status,
)
from service.connectors import registry
from service.credentials import encrypt_credentials
from service.provider_keys import CONNECTOR_TYPE as PROVIDER_KEY_TYPE

router = APIRouter(tags=["user-connectors"])

ALLOWED_CONNECTOR_TYPES = {
    "google_ads", "ga4", "gsc", "gtm",
    # Manual-credential connectors (Phase 7) — Fernet JSON blobs fit any shape.
    "apple_ads", "meta_ads", "stripe", "revenuecat", "openai_ads",
    # Gads wave 2 — the cross-check + behaviour sources.
    "mixpanel", "clarity", "growthbook",
}


class ConnectorIn(BaseModel):
    connector_type: str          # 'google_ads' | 'ga4' | 'gsc' | 'gtm'
    account_id: str = ""         # customer_id / property_id / site_url
    account_name: str = ""
    credentials: dict            # raw dict — will be encrypted at rest
    # What the provider actually consented to, space-separated. Optional: a
    # manual-credential save has none, and an OAuth save made by an older client
    # has none either — both correctly land as "unknown" rather than "none".
    granted_scopes: str = ""


class ConnectorOut(BaseModel):
    id: UUID
    connector_type: str
    account_id: str
    account_name: str
    last_validated_at: str | None
    created_at: str
    updated_at: str
    # The scope picture, joined here so the browser needs no catalog of its own:
    # `scopes` carries one row per scope this connector asks for, each with the
    # justification the user is entitled to read before granting it.
    granted_scopes: list[str] = []
    missing_scopes: list[str] = []
    scope_status: str = SCOPE_NA
    scopes: list[dict] = []



def _to_out(c: ConnectorCredential) -> ConnectorOut:
    entry = registry().get(c.connector_type)
    declared = parse_scopes(entry[0].oauth_scope) if entry else []
    granted = parse_scopes(c.granted_scopes)
    is_oauth = bool(entry and entry[0].oauth_scope)
    return ConnectorOut(
        id=c.id,
        connector_type=c.connector_type,
        account_id=c.account_id,
        account_name=c.account_name,
        last_validated_at=c.last_validated_at.isoformat() if c.last_validated_at else None,
        created_at=c.created_at.isoformat(),
        updated_at=c.updated_at.isoformat(),
        granted_scopes=granted,
        missing_scopes=missing_scopes(declared, granted) if (is_oauth and granted) else [],
        scope_status=scope_status(is_oauth=is_oauth, declared=declared, granted=granted),
        scopes=scope_rows(declared, granted) if is_oauth else [],
    )


@router.get("")
def list_connectors(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ConnectorOut]:
    rows = session.execute(
        select(ConnectorCredential)
        .where(ConnectorCredential.user_id == user.id)
        # Saved LLM provider keys share this table (service/provider_keys.py)
        # but are not connectors: no registry entry, no adapter, no account to
        # bind. Without this they surface here as a phantom row the Connections
        # page would render as a data source nobody can configure.
        .where(ConnectorCredential.connector_type != PROVIDER_KEY_TYPE)
        .order_by(ConnectorCredential.connector_type, ConnectorCredential.account_name)
    ).scalars().all()
    return [_to_out(r) for r in rows]



@router.get("/data-sources")
def list_account_data_sources(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """The same inventory as the project route, with no project in the picture.

    Needed because the first thing the onboarding checklist asks for is a
    PROJECT: someone who has connected three sources but not yet created one
    has no project id to ask about, and telling them they have connected
    nothing is how they end up connecting a fourth.

    Without a project there are no bindings, so every stored connector reports
    ``available`` rather than ``bound`` — which is the truth: the credential
    exists, nothing has chosen an account for it yet.
    """
    return [source.as_dict() for source in list_data_sources(session, user_id=user.id)]


@router.post("", status_code=201)
def save_connector(
    body: ConnectorIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConnectorOut:
    if body.connector_type not in ALLOWED_CONNECTOR_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown connector type: {body.connector_type!r}")

    account_id = body.account_id.strip()

    # Upsert by (user_id, connector_type, account_id)
    existing = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user.id,
            ConnectorCredential.connector_type == body.connector_type,
            ConnectorCredential.account_id == account_id,
        )
    ).scalars().first()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    enc = encrypt_credentials(body.credentials)

    granted = join_scopes(parse_scopes(body.granted_scopes))

    if existing:
        existing.account_name = body.account_name
        existing.credentials_enc = enc
        # Only overwrite when this save actually carries a grant. A later save
        # that does not know the scopes (an account rename, a manual re-save)
        # must not erase what the OAuth round-trip recorded.
        if granted:
            existing.granted_scopes = granted
        existing.updated_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return _to_out(existing)

    row = ConnectorCredential(
        user_id=user.id,
        connector_type=body.connector_type,
        account_id=account_id,
        account_name=body.account_name,
        credentials_enc=enc,
        granted_scopes=granted,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{connector_id}", status_code=204)
def delete_connector(
    connector_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    row = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.id == connector_id,
            ConnectorCredential.user_id == user.id,
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Connector not found")
    session.delete(row)
    session.commit()
