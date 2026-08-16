"""Project collaboration models — members and email invitations.

A project is the only shareable object in the product (there is no org or
workspace entity), so collaboration is modelled directly against it:

- ``ProjectMember`` — the access list. Every project has exactly one ``owner``
  row (backfilled from ``projects.user_id``, which stays the owner column) plus
  zero or more ``collaborator`` rows.
- ``ProjectInvitation`` — a pending grant addressed to an email, redeemable once
  by whoever signs in with that address. Only the SHA-256 hash of the token is
  stored; the plaintext exists solely in the emailed link.

Roles are deliberately a two-value string rather than an enum table. Adding
``viewer`` / ``admin`` later means widening the check constraint, not migrating
a join table.
"""

from __future__ import annotations

from datetime import datetime, timezone
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
from sqlmodel import Field, SQLModel

ROLE_OWNER = "owner"
ROLE_COLLABORATOR = "collaborator"
PROJECT_ROLES = (ROLE_OWNER, ROLE_COLLABORATOR)

INVITE_PENDING = "pending"
INVITE_ACCEPTED = "accepted"
INVITE_REVOKED = "revoked"
INVITE_STATUSES = (INVITE_PENDING, INVITE_ACCEPTED, INVITE_REVOKED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectMember(SQLModel, table=True):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        CheckConstraint(
            "role IN ('owner', 'collaborator')",
            name="ck_project_members_role_allowed",
        ),
        # One owner per project — the invariant every permission check leans on.
        Index(
            "uq_project_members_single_owner",
            "project_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    role: str = Field(
        default=ROLE_COLLABORATOR,
        sa_column=Column(String, nullable=False, server_default=ROLE_COLLABORATOR),
    )
    # Null for owner rows created by backfill; set to the inviter for accepted invites.
    invited_by_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProjectInvitation(SQLModel, table=True):
    __tablename__ = "project_invitations"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_project_invitations_email_lowercase"),
        CheckConstraint(
            "role IN ('owner', 'collaborator')",
            name="ck_project_invitations_role_allowed",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked')",
            name="ck_project_invitations_status_allowed",
        ),
        # At most one live invite per (project, email); revoked/accepted rows stay
        # as history and are excluded so the same address can be re-invited.
        Index(
            "uq_project_invitations_pending_email",
            "project_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_project_invitations_email_status", "email", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    email: str = Field(sa_column=Column(String, nullable=False))
    role: str = Field(
        default=ROLE_COLLABORATOR,
        sa_column=Column(String, nullable=False, server_default=ROLE_COLLABORATOR),
    )
    # SHA-256 of the plaintext token. Unique so a redeem is a single indexed
    # lookup and a collision can never map one token to two invitations.
    token_hash: str = Field(sa_column=Column(String, nullable=False, unique=True, index=True))
    invited_by_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    status: str = Field(
        default=INVITE_PENDING,
        sa_column=Column(String, nullable=False, server_default=INVITE_PENDING),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    accepted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    accepted_by_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    last_sent_at: datetime | None = Field(
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
