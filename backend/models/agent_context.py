"""Agent context persistence model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from models.columns import json_column, utc_datetime
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


class AgentContext(SQLModel, table=True):
    __tablename__ = "agent_contexts"
    __table_args__ = (
        UniqueConstraint("project_id", "agent_id", name="uq_agent_contexts_project_agent"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    # Human-readable internal agent identifier, e.g. 'audit_seo', 'insights'
    agent_id: str = Field(sa_column=Column(String, nullable=False))
    data: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
