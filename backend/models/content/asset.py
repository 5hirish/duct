"""Content asset (generated images, uploads, references)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentAsset(SQLModel, table=True):
    __tablename__ = "content_assets"
    __table_args__ = (
        Index("ix_content_assets_project_type", "project_id", "asset_type"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    post_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("content_posts.id", ondelete="SET NULL"), nullable=True),
    )
    asset_type: str = Field(sa_column=Column(String, nullable=False))
    source: str = Field(default="upload", sa_column=Column(String, nullable=False, server_default="upload"))
    url: str = Field(sa_column=Column(String, nullable=False))
    filename: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    mime_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    prompt: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    model: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    params: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
