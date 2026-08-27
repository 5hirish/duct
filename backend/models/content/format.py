"""Per-project content format library entry."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from models.columns import json_column
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


class ContentFormat(SQLModel, table=True):
    __tablename__ = "content_formats"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_content_formats_project_slug"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    slug: str = Field(sa_column=Column(String, nullable=False))
    name: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    data: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
