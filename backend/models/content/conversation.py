"""Agent conversation persistence — chat history + resume state.

Sessions used to live only in RAM (agents/core/session.py), so a pruned /
closed / redeployed session lost its chat history and the agent's working
memory. These two tables persist the *conversation* (not the artifact — the
post/plan already lives in content_posts / content_plans) so a session can be
rebuilt on resume by re-priming a fresh SDK session from the DB.

Design notes
------------
- The conversation↔artifact link is **polymorphic** (``artifact_type`` +
  ``artifact_id``, no FK) so this scales to any agent / any artifact type
  without a schema change. A small registry resolves (agent_type, artifact_type)
  → table. Orphan cleanup on artifact delete is therefore app-level.
- ``agent_events`` is a generic, schemaless, append-only log: ``kind`` is a free
  string (not a DB enum) and ``data`` is JSONB, so new message/event types need
  zero migrations.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from models.columns import json_column
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


class AgentConversation(SQLModel, table=True):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        # At most one ACTIVE conversation per artifact — the "click post → resume"
        # lookup relies on this. Partial unique index lets archived rows pile up.
        Index(
            "uq_agent_conv_active_artifact",
            "artifact_type",
            "artifact_id",
            unique=True,
            postgresql_where=sa.text(
                "status = 'active' AND artifact_id IS NOT NULL"
            ),
        ),
        Index("ix_agent_conv_project_status", "project_id", "status"),
        Index("ix_agent_conv_artifact", "agent_type", "artifact_type", "artifact_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    # No default — set explicitly per session (e.g. "tiktok_studio").
    agent_type: str = Field(sa_column=Column(String, nullable=False))
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    # SDK-config dispatch discriminator on resume ("plan_month" | "draft_post").
    mode: str = Field(default="draft_post", sa_column=Column(String, nullable=False, server_default="draft_post"))

    # Polymorphic artifact link — NO FK (points across content_posts / content_plans
    # / future tables). (agent_type, artifact_type) resolves which table.
    artifact_type: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    artifact_id: UUID | None = Field(
        default=None, sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    )

    title: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # "active" | "archived" — start-fresh archives the old, the partial index
    # then frees up so a new active conversation can claim the artifact.
    status: str = Field(default="active", sa_column=Column(String, nullable=False, server_default="active"))

    # Running compaction state — summary covers events up to summary_through_seq.
    summary: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    summary_through_seq: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))

    # Atomic per-conversation seq allocator (UPDATE ... SET last_seq = last_seq + 1
    # ... RETURNING last_seq) — no MAX+1 race.
    last_seq: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))

    input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    output_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))

    # Catch-all for forward fields so new agent needs don't always need a migration.
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_active_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AgentEvent(SQLModel, table=True):
    """Generic, schemaless, append-only conversation log (one row per turn).

    ``kind`` is a free string (user/assistant/thinking/tool_use/question/answer/…)
    and ``data`` is JSONB ({"text": ...} / {"questions": [...]} / {"name", "input"}
    / whatever the kind needs). Adding a new kind never touches the schema.
    """

    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_agent_events_conv_seq"),
        Index("ix_agent_events_conv_seq", "conversation_id", "seq"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    conversation_id: UUID = Field(
        sa_column=Column(
            ForeignKey("agent_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    seq: int = Field(sa_column=Column(Integer, nullable=False))
    kind: str = Field(sa_column=Column(String, nullable=False))
    data: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
