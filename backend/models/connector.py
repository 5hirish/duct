"""Connector credential persistence model."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class ConnectorType(StrEnum):
    """The external services a user can connect — ConnectorCredential.connector_type.

    Stored as a plain String column (values match these members); use this enum
    in code instead of bare strings. The Google connector ids are also exposed as
    GOOGLE_ADS_CONNECTOR_ID / GA4_CONNECTOR_ID / GSC_CONNECTOR_ID in
    service/google/constants.py (same values) for the OAuth-callback subsystem.
    """

    POST_BRIDGE = "post_bridge"   # social publishing + analytics
    HIGGSFIELD  = "higgsfield"    # video generation
    GOOGLE_ADS  = "google_ads"
    GA4         = "ga4"
    GSC         = "gsc"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
