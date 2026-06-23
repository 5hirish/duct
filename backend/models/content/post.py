"""Individual content post persistence model."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
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
    post_dir_slug: str = Field(sa_column=Column(String, nullable=False))

    pillar: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    topic: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    topic_id: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    post_type: str = Field(default="slideshow", sa_column=Column(String, nullable=False, server_default="slideshow"))
    # The format this post was built with. Posts link to the format library by
    # this FK only (the legacy free-text format_style selector was removed).
    format_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("content_formats.id", ondelete="SET NULL"), nullable=True, index=True
        ),
    )
    avatar_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("content_avatars.id", ondelete="SET NULL"), nullable=True),
    )

    slide_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    status: str = Field(default="pending", sa_column=Column(String, nullable=False, server_default="pending"))

    # Overall layout family (full-bleed | text-only | collage | before-after |
    # editorial). Denormalised from the format so render is self-contained.
    layout: str = Field(default="full-bleed", sa_column=Column(String, nullable=False, server_default="full-bleed"))
    # Structured per-slide content authored by the agent — the SOURCE OF TRUTH.
    # slides_html below is DERIVED from this by the template renderer. Each entry
    # carries copy, the image prompt, and (once generated) image_url +
    # image_prompt_used for staleness. See agents/content/schema.py:Slide.
    slides: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    slides_html: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    caption: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    hashtags: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    tiktok_title: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    hook_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    hook_text: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    hook_emotion: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    save_cta: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    bridge_text: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    image_prompts: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    audio_note: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    strategic_note: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    visual_brief: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    emotional_arc: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    camera_ref_pool: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    platforms: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )

    # Video (single-clip) — populated only when post_type == "video". The clip is
    # generated via Higgsfield (service/higgsfield) and stored as a content_assets
    # row; these denormalise the chosen clip + its generation inputs onto the post
    # so render + publish are self-contained. slides[] stays empty for video posts.
    video_url: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    video_asset_id: UUID | None = Field(default=None, sa_column=Column(Uuid, nullable=True))
    video_prompt: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    video_duration_seconds: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    video_aspect_ratio: str = Field(default="9:16", sa_column=Column(String, nullable=False, server_default="9:16"))
    # The keyframe still (a content_assets id) that was animated into the clip.
    source_image_asset_id: UUID | None = Field(default=None, sa_column=Column(Uuid, nullable=True))
    # Multi-beat storyboard for video posts — ordered shots, each carrying its
    # keyframe prompt + (once generated) keyframe asset id/url, mirroring slides[].
    # The keyframe images themselves are normal content_assets rows in the same
    # projects/{id}/generated/ bucket path. See agents/content/schema.py:VideoBeat.
    video_storyboard: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )

    posted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # When the post is scheduled to publish (set via the publish flow). Drives
    # the calendar/week placement and the "scheduled" date badge.
    scheduled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    tiktok_url: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # Provenance: "duct" when the post went out through our system (Duct publish
    # flow or a migrated MaxAura plan); "" / "external" when it appeared on the
    # account from elsewhere (TikTok Studio, PostBridge dashboard).
    published_via: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
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
    # Latest pre-publish review (PublishAssessment.model_dump): overall score,
    # band, sanity checks, marker scores. None until a review runs. Persisted so
    # the panel survives reload and shows on the read-only detail page.
    last_assessment: dict | None = Field(
        default=None,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=True),
    )
    notes: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))

    # Clone/reference lineage for posts added via the board's Add-post flow.
    # None for ordinary planner/manual posts. Holds the source pointer + a cache
    # of the (expensive) Apify ingest so re-drafting never re-charges:
    #   {kind: "manual"|"url"|"reference", url, reference_asset_id, ingested,
    #    scraped_post, media: {cover, slides[]}, diagnostic, ingested_at}
    # See agents/content/v3/runner.py:_run_clone_worker (ingest is deferred to the
    # first Draft-now, then cached here).
    clone_source: dict | None = Field(
        default=None,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=True),
    )

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
