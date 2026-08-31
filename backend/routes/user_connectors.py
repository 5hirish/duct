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
from service.credentials import encrypt_credentials

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


class ConnectorOut(BaseModel):
    id: UUID
    connector_type: str
    account_id: str
    account_name: str
    last_validated_at: str | None
    created_at: str
    updated_at: str



def _to_out(c: ConnectorCredential) -> ConnectorOut:
    return ConnectorOut(
        id=c.id,
        connector_type=c.connector_type,
        account_id=c.account_id,
        account_name=c.account_name,
        last_validated_at=c.last_validated_at.isoformat() if c.last_validated_at else None,
        created_at=c.created_at.isoformat(),
        updated_at=c.updated_at.isoformat(),
    )


@router.get("")
def list_connectors(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ConnectorOut]:
    rows = session.execute(
        select(ConnectorCredential)
        .where(ConnectorCredential.user_id == user.id)
        .order_by(ConnectorCredential.connector_type, ConnectorCredential.account_name)
    ).scalars().all()
    return [_to_out(r) for r in rows]



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

    if existing:
        existing.account_name = body.account_name
        existing.credentials_enc = enc
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
