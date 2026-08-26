"""Structured activity log — the project's audit trail.

One row per *lifecycle transition* with actor attribution: change set
proposed/approved/applied/rolled back, artifact created/versioned, GTM
version published. Deliberately NOT a mirror of agent tool calls — raw tool
I/O stays in ``agent_events`` (conversation forensics); domain state stays on
``execution_change_sets`` / ``artifacts``. This table answers the third
question those can't: *what happened on this project, by whom, when* —
including human actions taken outside any conversation and transitions whose
timestamps the state rows overwrite.

Rows are append-only and written best-effort (service/activity.py) — logging
must never break the write it records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlmodel import Field, SQLModel

from models.columns import json_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Who performed the transition.
ACTIVITY_SOURCES = {"user", "agent", "auto"}

# What kind of thing happened. "conversation" and "connector" are reserved for
# follow-on call sites; wave 1 writes execution + artifact rows.
ACTIVITY_CATEGORIES = {"execution", "artifact", "conversation", "connector"}


class ActivityLog(SQLModel, table=True):
    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_project_created", "project_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    # Nullable: pre-project flows (e.g. /execute proposals without a project)
    # still log, scoped to the user alone.
    project_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True),
    )
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    # Polymorphic link to agent_conversations — no FK (artifacts convention).
    conversation_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=True, index=True),
    )
    agent_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    source: str = Field(default="user", sa_column=Column(String, nullable=False, server_default="user"))
    category: str = Field(sa_column=Column(String, nullable=False))
    # Dotted transition name, e.g. "change_set.proposed", "change_set.auto_applied",
    # "artifact.created", "gtm.published".
    action: str = Field(sa_column=Column(String, nullable=False))
    connector_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    account_id: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # Cross-link to the domain row: ("change_set", uuid) / ("artifact", uuid) / ...
    target_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    target_id: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # One human-readable line for the feed.
    summary: str = Field(default="", sa_column=Column(sa.Text(), nullable=False, server_default=""))
    # Small structured delta (e.g. prior/new GTM version ids) — not raw tool I/O.
    data: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
