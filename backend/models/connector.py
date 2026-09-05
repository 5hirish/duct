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
    # Which *entity* inside that account this project reads — a Search Console
    # property, a GA4 property, a Tag Manager container. One credential reaches
    # many of them, so the choice cannot live on the credential row: two
    # projects can share one Google sign-in and still mean different sites.
    #
    # Deliberately optional. Empty means "not chosen yet", which is a real and
    # common state, and the agent asks at the point it needs one rather than
    # the UI blocking a connection over a decision the user may not be ready to
    # make. Never infer a default from "there is only one" — that silently
    # picks for them and is wrong the moment a second appears.
    #
    # `entity_name` is denormalised on purpose: it is a display label, and
    # re-reading it means an API round trip per row on a page that renders
    # before any of them resolve. It can go stale; a stale label is a smaller
    # problem than a picker that renders empty.
    entity_id: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )
    entity_name: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )


# Where a credential is *allowed* to live, which is not the same question as
# where it currently is.
#
# `db.session.storage_location()` answers "where is this row", derived from the
# database this process is talking to. That is a fact about the deployment and
# it changes when the same sidecar is pointed somewhere else. This is the
# user's intent about one credential, it travels with the row, and it is what
# the write path enforces — otherwise "keep this on my machine" is a label
# rather than a rule, and a desktop build pointed at a shared database would
# quietly upload the thing it promised not to.
RESIDENCY_SERVER = "server"
RESIDENCY_DEVICE = "device"
RESIDENCIES = (RESIDENCY_SERVER, RESIDENCY_DEVICE)


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
    # Server by default: a credential that cannot be reached without a browser
    # open is useless to a scheduled brief, and that is most of what Duct does.
    # Device is the deliberate exception, and the save path refuses to write one
    # into a database this machine does not own.
    residency: str = Field(
        default=RESIDENCY_SERVER,
        sa_column=Column(String, nullable=False, server_default=RESIDENCY_SERVER),
    )
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
