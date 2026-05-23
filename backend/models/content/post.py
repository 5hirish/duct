"""Individual content post persistence model."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentPost(SQLModel, table=True):
    __tablename__ = "content_posts"
    __table_args__ = (
        UniqueConstraint("project_id", "post_dir_slug", name="uq_content_posts_project_slug"),
        Index("ix_content_posts_project_status", "project_id", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    plan_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("content_plans.id", ondelete="SET NULL"), nullable=True),
    )
    day_index: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    post_dir_slug: str = Field(sa_column=Column(String, nullable=False))

    pillar: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    topic: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    topic_id: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    post_type: str = Field(default="slideshow", sa_column=Column(String, nullable=False, server_default="slideshow"))
    format_style: str = Field(default="D", sa_column=Column(String, nullable=False, server_default="D"))
    avatar_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("content_avatars.id", ondelete="SET NULL"), nullable=True),
    )

    slide_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    status: str = Field(default="pending", sa_column=Column(String, nullable=False, server_default="pending"))

    slides_html: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    caption: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    hashtags: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    tiktok_title: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    hook_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    hook_text: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    image_prompts: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    audio_note: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    platforms: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )

    posted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    tiktok_url: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    post_bridge_post_id: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    post_bridge_result_id: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    perf: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    daily_perf: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    notes: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
