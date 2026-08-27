"""Auth-first persistence models (Google sign-in)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from models.columns import json_column
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    email: str = Field(
        sa_column=Column(String, nullable=False, unique=True, index=True)
    )
    full_name: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    avatar_url: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    last_sign_in_at: datetime | None = Field(
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


class AuthIdentity(SQLModel, table=True):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_auth_identity_provider_user"),
        CheckConstraint("provider IN ('google')", name="ck_auth_identities_provider_allowed"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    provider: str = Field(sa_column=Column(String, nullable=False))
    provider_user_id: str = Field(sa_column=Column(String, nullable=False))
    provider_email: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    raw_profile: dict | None = Field(
        default=None, sa_column=Column(json_column(), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class OAuthState(SQLModel, table=True):
    __tablename__ = "oauth_states"
    __table_args__ = (
        Index("ix_oauth_states_expires_at", "expires_at"),
        Index(
            "ix_oauth_states_unconsumed_expires_at",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    state: str = Field(sa_column=Column(String, primary_key=True, nullable=False))
    flow: str = Field(sa_column=Column(String, nullable=False, index=True))
    code_verifier: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    issued_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    consumed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

