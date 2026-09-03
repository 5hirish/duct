"""Connector credential persistence model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel
from models.columns import utc_datetime
from utils.dates import utcnow


class ProjectConnector(SQLModel, table=True):
    """Per-project connector→account binding.

    Credentials stay per-user in ``connector_credentials`` (deduplicated —
    two projects sharing one Stripe account share one encrypted row); this
    table decides WHICH of a user's accounts a project uses. One binding per
    (project, connector_type). Resolution order lives in
    ``service/execution/creds.py``: project binding → caller's user rows →
    env. Binding a credential requires project membership AND owning the
    credential row; using it requires only membership — that is the point:
    a collaborator's agent run uses the project's account, not their own.
    """

    __tablename__ = "project_connectors"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "connector_type",
            name="uq_project_connectors_project_type",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    connector_type: str = Field(sa_column=Column(String, nullable=False))
    # CASCADE: deleting the credential (user disconnects the account) removes
    # its bindings, so projects fall back to user-level resolution.
    connector_credential_id: UUID = Field(
        sa_column=Column(
            ForeignKey("connector_credentials.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    created_by_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )


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
    # Space-separated scopes the provider ACTUALLY granted, as OAuth itself
    # writes them. Its own column rather than a field inside credentials_enc
    # because it is not a secret and the data-source inventory reads it on every
    # page load — putting it in the blob would mean decrypting every row to
    # answer "is this connector fully authorized?". Empty for manual-credential
    # connectors, and for OAuth rows stored before grants were recorded: empty
    # means "unknown", never "none".
    granted_scopes: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )
    last_validated_at: datetime | None = Field(
        default=None, sa_column=Column(utc_datetime(), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
