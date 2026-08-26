"""Versioned artifact store — durable agent outputs.

An *artifact* is anything an agent produces for the user: an audit report, a
document, a ticket, an image. Claude-style identity: ``group_id`` is the stable
artifact identity, each row is one immutable version of it (``UNIQUE(group_id,
version)``); the newest version is the current one.

Content lives in two places:
  - ``structured_json`` — typed payload for template-rendered artifacts (e.g.
    the audit report's StructuredAuditData); rendered by the app, never by us.
  - ``storage_key``     — private object storage (R2 / local disk) for raw
    bytes (freehand HTML, PDFs, images). Served ONLY through the authed
    ``/api/user/artifacts/{id}/content`` endpoint — never a public URL.

``conversation_id`` is a polymorphic many-to-one link (no FK, same rationale as
``agent_conversations.artifact_id``): one conversation can produce many
artifacts. ``summary`` is an AI-written context digest so later agent sessions
can cite prior artifacts without loading them whole.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.columns import json_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("group_id", "version", name="uq_artifacts_group_version"),
        Index("ix_artifacts_project_created", "project_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    # Stable identity across versions; minted with the first version.
    group_id: UUID = Field(
        sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, index=True)
    )
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False, server_default="1"))

    project_id: UUID = Field(
        sa_column=Column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    # Polymorphic link to agent_conversations — NO FK (see module docstring).
    conversation_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=True, index=True),
    )

    # Model-chosen kebab-case identity, unique per project among groups ("" =
    # unnamed). Shared by every version of the group; app-enforced uniqueness
    # (ensure_unique_slug) — no DB constraint since version rows repeat it.
    slug: str = Field(default="", sa_column=Column(String, nullable=False, server_default="", index=True))

    agent_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # Semantic kind: 'report' | 'document' | 'ticket' | 'image' | ...
    kind: str = Field(
        default="report", sa_column=Column(String, nullable=False, server_default="report")
    )
    # MIME type of the content: text/html, application/json, text/markdown, ...
    content_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    title: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    filename: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    storage_key: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    size_bytes: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    checksum: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    # Template-rendered payload (e.g. AuditReport minus html_report); {} otherwise.
    structured_json: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    # AI context digest for future agent sessions ("" until the summarizer lands).
    summary: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    # Display metadata for list cards: scores, counts, source window.
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
