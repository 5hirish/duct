"""Pydantic schemas + dataclasses for the Content Marketing Agent.

Two groups:
  - Domain shapes — ported from nomadapps/marketing/app/src/types.ts
    (Character, Perf, Day, Avatar, AppContext → ContentBrandContext).
  - Wire shapes — request/session models the route layer uses.
  - Sub-agent output schemas — TopicCandidates, PostDraft, PlanDraft.
    Used inside writer @tools to validate JSON the orchestrator passes in.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agents.models import AspectRatio, ImageModel, Platform


# ---------------------------------------------------------------------------
# Domain shapes (ports of marketing/app/src/types.ts)
# ---------------------------------------------------------------------------


class Character(BaseModel):
    """Persona narrating the 30-day plan; written into ContentPlan.character."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    age_range: str = ""
    look: str = ""
    voice: str = ""
    notes: str = ""


class Perf(BaseModel):
    """Per-post performance snapshot mirrored from PostBridge analytics."""

    model_config = ConfigDict(extra="forbid")

    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    save_count: int | None = None
    completion_rate: float | None = None
    profile_visits: int | None = None
    bio_link_clicks: int | None = None
    comments_1h: int | None = None
    save_rate: float | None = None
    last_synced_at: datetime | None = None


class Day(BaseModel):
    """One entry in ContentPlan.days[]."""

    model_config = ConfigDict(extra="forbid")

    day: int = Field(ge=1, le=31)
    topic_id: str | None = None
    topic: str = ""
    pillar: str = ""
    status: Literal["pending", "draft", "posted", "discarded"] = "pending"
    post_type: Literal["slideshow", "video", "image"] = "slideshow"
    post_id: UUID | None = None
    format_style: str = "D"
    avatar_id: UUID | None = None
    platforms: list[Platform] = Field(default_factory=lambda: [Platform.TIKTOK])


class AvatarRefCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID | None = None
    url: str = ""
    description: str = ""


class Avatar(BaseModel):
    """Per-project on-camera persona — ports marketing types.ts Avatar."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    face_refs: list[AvatarRefCell] = Field(default_factory=list)
    body_refs: list[AvatarRefCell] = Field(default_factory=list)


class AppFeature(BaseModel):
    """Brand feature, e.g. 'face_shape', 'color_aura'."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""


class ContentPillar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    research_hint: str | None = None


class ContentVisualAssets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logo_url: str = ""
    background_urls: list[str] = Field(default_factory=list)
    primary_color: str = ""
    secondary_color: str = ""
    style: str = ""


class ContentBrandContext(BaseModel):
    """Top-level brand snapshot the orchestrator references in every prompt."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    project_name: str = ""
    slug: str = ""
    tagline: str = ""
    description: str = ""
    url: str = ""
    audience: str = ""
    brand_voice: str = ""
    value_prop: str = ""
    content_goal: str = ""
    features: list[AppFeature] = Field(default_factory=list)
    pillars: list[ContentPillar] = Field(default_factory=list)
    visual: ContentVisualAssets = Field(default_factory=ContentVisualAssets)


# ---------------------------------------------------------------------------
# Wire shapes — route requests, session, run mode
# ---------------------------------------------------------------------------


RunMode = Literal["plan_month", "draft_post"]


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    start_date: date | None = None


class DraftPostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    plan_id: UUID | None = None
    day_index: int | None = None
    topic: str | None = None
    pillar: str | None = None


class ContentAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str]


class ContentChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | list


@dataclass
class ContentSession:
    """Per-session state — mirrors AuditSession at agents/audit/schema.py."""

    session_id: str
    project_id: UUID
    mode: RunMode
    event_queue: Any                  # asyncio.Queue — agent → SSE consumer
    chat_queue: Any                   # asyncio.Queue — user follow-ups → agent
    answer_future: Any | None = None  # asyncio.Future | None — AskUserQuestion bridge
    plan_id: UUID | None = None
    post_id: UUID | None = None
    created_at: float = 0.0
    todos: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-agent output schemas (validated inside writer @tools)
# ---------------------------------------------------------------------------


class TopicCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    title: str
    angle: str
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class TopicCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pillar_id: str
    items: list[TopicCandidate]


# ---------------------------------------------------------------------------
# Pre-flight research context — populated by enrichment.py between
# project-load and the orchestrator's first user turn. Borrowed from the
# audit agent's AuditResearchContext pattern.
# ---------------------------------------------------------------------------


class PillarHistorySignal(BaseModel):
    """Local-only signal computed from already-persisted content_posts.

    Lets the orchestrator (and downstream draft sub-agents) avoid
    repeating topics or under-using pillars without paying for web
    research.
    """

    model_config = ConfigDict(extra="forbid")

    pillar:                  str
    posts_count:             int = 0
    days_since_last_post:    int | None = None       # None = never used
    recent_topics:           list[str] = Field(default_factory=list)
    recent_hook_types:       list[str] = Field(default_factory=list)
    median_save_rate:        float | None = None     # if perf data exists


class TrendSignal(BaseModel):
    """One trending element worth riding this week. The sub-agent fills
    these from WebSearch / WebFetch results."""

    model_config = ConfigDict(extra="forbid")

    kind:        str               # "sound" | "hashtag" | "hook" | "style" | "format"
    label:       str               # human-readable name or hashtag
    why_it_works: str = ""         # 1 sentence on why this fits the audience
    evidence_url: str | None = None  # where the sub-agent saw it trending


class ContentResearchContext(BaseModel):
    """Output of the pre-flight enrichment sub-agent.

    Local signals are always populated (cheap). Trend signals + audience
    insights are populated only if the sub-agent succeeds — caller treats
    missing fields as "no enrichment available" and proceeds.
    """

    model_config = ConfigDict(extra="forbid")

    # Local signals — extracted from content_posts at no cost.
    pillar_history:           list[PillarHistorySignal] = Field(default_factory=list)
    total_posts_to_date:      int = 0
    days_since_last_post:     int | None = None

    # Sub-agent research — fill when WebSearch + WebFetch return useful results.
    trending_sounds:          list[TrendSignal] = Field(default_factory=list)
    trending_hashtags:        list[TrendSignal] = Field(default_factory=list)
    trending_hooks:           list[TrendSignal] = Field(default_factory=list)
    trending_styles:          list[TrendSignal] = Field(default_factory=list)
    audience_insights:        list[str] = Field(default_factory=list)
    enrichment_notes:         list[str] = Field(default_factory=list)


class ImagePrompt(BaseModel):
    """One image slot inside a slide. The runner passes `prompt` to Gemini."""

    model_config = ConfigDict(extra="forbid")

    slide_id: str
    prompt: str
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    model: ImageModel | None = None


class PostDraft(BaseModel):
    """One draft post coming back from the draft_post sub-agent or orchestrator.

    `type` discriminator keeps PlanDraft and PostDraft distinguishable inside
    the <duct_report> tag.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["post"] = "post"
    project_id: UUID
    post_dir_slug: str
    pillar: str
    topic: str
    topic_id: str | None = None
    post_type: Literal["slideshow", "video", "image"] = "slideshow"
    format_style: str = "D"
    avatar_id: UUID | None = None
    slide_count: int = Field(default=7, ge=1, le=20)
    slides_html: str
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    hook_type: str = ""
    hook_text: str = ""
    tiktok_title: str = ""
    image_prompts: list[ImagePrompt] = Field(default_factory=list)
    audio_note: str | None = None
    strategic_note: str = ""           # 1-2 sentences: why this post works in the broader strategy
    platforms: list[Platform] = Field(default_factory=lambda: [Platform.TIKTOK])


class PlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["plan"] = "plan"
    project_id: UUID
    name: str = ""
    start_date: date | None = None
    character: Character = Field(default_factory=Character)
    days: list[Day]


# ---------------------------------------------------------------------------
# Convenience for session construction
# ---------------------------------------------------------------------------


def make_session(
    session_id: str,
    project_id: UUID,
    mode: RunMode,
) -> ContentSession:
    """Build a ContentSession with fresh asyncio queues."""
    import time
    return ContentSession(
        session_id=session_id,
        project_id=project_id,
        mode=mode,
        event_queue=asyncio.Queue(),
        chat_queue=asyncio.Queue(),
        answer_future=None,
        created_at=time.monotonic(),
    )


__all__ = [
    "AppFeature",
    "Avatar",
    "AvatarRefCell",
    "Character",
    "ContentAnswerRequest",
    "ContentBrandContext",
    "ContentChatMessage",
    "ContentPillar",
    "ContentResearchContext",
    "ContentSession",
    "ContentVisualAssets",
    "Day",
    "DraftPostRequest",
    "ImagePrompt",
    "Perf",
    "PillarHistorySignal",
    "PlanDraft",
    "PlanRequest",
    "PostDraft",
    "RunMode",
    "TopicCandidate",
    "TopicCandidates",
    "TrendSignal",
    "make_session",
]
