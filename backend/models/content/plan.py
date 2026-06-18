"""30-day content plan persistence model."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentPlan(SQLModel, table=True):
    __tablename__ = "content_plans"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    name: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    start_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    character: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    days: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    # Strategist narrative — written by the content_planner agent. Holds the
    # long-term arc (narrative_arc), why-this-order (sequencing_rationale), and
    # the content-type mix so each weekly refresh can continue the thread.
    strategy: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    status: str = Field(default="draft", sa_column=Column(String, nullable=False, server_default="draft"))
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
