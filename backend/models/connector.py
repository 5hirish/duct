"""Connector credential persistence model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


class ConnectorCredential(SQLModel, table=True):
    __tablename__ = "connector_credentials"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "connector_type", "account_id",
            name="uq_connector_credentials_user_type_account",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    # e.g. 'google_ads' | 'ga4' | 'gsc'
    connector_type: str = Field(sa_column=Column(String, nullable=False))
    # customer_id for Google Ads, property_id for GA4, site_url for GSC
    account_id: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    account_name: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # AES-encrypted JSON blob — encryption key lives in CREDENTIALS_ENCRYPTION_KEY env var
    credentials_enc: str = Field(sa_column=Column(String, nullable=False))
    last_validated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
