"""Pydantic schemas + dataclasses for the Content Studio agent.

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
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agents.core.session import BaseAgentSession

from agents.content.channels import Platform
from agents.models import AspectRatio, ImageModel


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
    """One entry in ContentPlan.days[] — an ordered content item for the month.

    Items are ordered by their position in the list; there is no day number.
    The calendar lays them out on sequential dates from the 1st of the month.

    extra="ignore": stored/legacy day objects may carry extra planning fields
    (notes, hook_text, save_cta, a legacy `day` index) that this shape doesn't
    model — tolerate and drop them rather than failing validation.
    """

    model_config = ConfigDict(extra="ignore")

    topic_id: int | str | None = None
    topic: str = ""
    pillar: str = ""
    status: Literal["pending", "draft", "posted", "discarded"] = "pending"
    post_type: Literal["slideshow", "video", "image"] = "slideshow"
    post_id: UUID | None = None
    format_slug: str = ""   # which library format to build with (e.g. "format-d")
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
    tone: str = ""
    value_prop: str = ""
    content_goal: str = ""
    do_say: str = ""
    do_not_say: str = ""
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
    channel: str | None = None   # primary platform (platforms[0]); selects the agent playbook


class ContentAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str]


class ContentChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | list


@dataclass(kw_only=True)
class ContentSession(BaseAgentSession):
    """Per-session state — BaseAgentSession (session_id, agent_type, queues,
    answer_future, created_at, pipeline_task) plus content-specific fields."""

    project_id: UUID
    mode: RunMode
    plan_id: UUID | None = None
    post_id: UUID | None = None
    # Persisted-conversation linkage (session resume / chat history). Set by the
    # route layer when a session is created; the runner re-primes from the DB when
    # resume is True. recorder persists each turn (agents/content/persistence.py).
    conversation_id: UUID | None = None
    recorder: Any = None
    resume: bool = False
    # On resume we don't run a greeting turn; the restored context (resume_primer)
    # is prepended to the user's FIRST chat message instead. needs_reprime gates
    # that one-time injection (see routes.agents.send_message).
    needs_reprime: bool = False
    resume_primer: str = ""
    todos: list[dict] = field(default_factory=list)
    # render_id -> asyncio.Future, resolved by the frontend's slide-render POST.
    # Bridges the agent's render_slide tool to client-side rasterization (same
    # pattern as answer_future for AskUserQuestion).
    render_futures: dict = field(default_factory=dict)
    # Messages typed while a turn is running. The V1 runner mounts
    # SteerMiddleware over this queue, so a mid-turn message reaches the model
    # at its next call instead of waiting for the turn to end.
    steer_queue: Any | None = None
    # The Gemini key this run may spend on images — a *different* provider from
    # the one driving the conversation, so it is resolved separately and can be
    # absent while the run itself is fine (the image tools then decline).
    # Empty is not "use the server's": the resolver already decided that, and
    # the tools must never reach past it to config. See routes/content.py
    # ::_resolve_image_key and agents/engines.resolve_provider_key.
    gemini_api_key: str = ""


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
    """One image slot inside a slide. The runner passes `prompt` to Gemini.

    Legacy/derived shape: with the structured-slides model the orchestrator
    authors prompts on each Slide; submit_post_draft DERIVES this flat list
    from slides so the DB column + frontend keep working unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    slide_id: str
    prompt: str
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    model: ImageModel | None = None


# ---------------------------------------------------------------------------
# Structured slide content — the source of truth the orchestrator authors.
# Python renders slides_html DETERMINISTICALLY from these via templates.py;
# the model never writes raw HTML. See agents/content/templates.py.
# ---------------------------------------------------------------------------


class SlideLayout(StrEnum):
    """Overall post layout family — picks the template set + CSS aesthetic.

    Mirrors the reference library's `layouts` axis
    (data/content/references/README.md). The orchestrator returns one per
    post; individual slides may still vary their `kind`.
    """

    FULL_BLEED   = "full-bleed"     # single photo + text overlay — the duct default
    TEXT_ONLY    = "text-only"      # dark bg, big statement, no photo (use sparingly)
    COLLAGE      = "collage"        # 2×2 educational grid + serif label
    BEFORE_AFTER = "before-after"   # do/don't split — two images, ❌/✅
    EDITORIAL    = "editorial"      # styled shoot, ivory bg, product lineup


class ContentStatus(StrEnum):
    """Lifecycle of a content post — ContentPost.status (and Day.status).

    Stored as a plain String column (values match these members); use this enum
    in code instead of bare strings. Mirrored on the frontend in
    app/src/lib/contentStatus.js.

    PENDING   — agent drafted it, but the user hasn't saved/kept it yet.
                Hidden from the board + the agent's topic-bank/history reads.
    DRAFT     — user clicked Save; now a real, kept draft.
    SCHEDULED — queued to publish.
    POSTED    — published.
    DISCARDED — rejected.
    """

    PENDING   = "pending"
    DRAFT     = "draft"
    SCHEDULED = "scheduled"
    POSTED    = "posted"
    DISCARDED = "discarded"


class ContentTool(StrEnum):
    """Names of the content tools as the model sees them.

    ``agents/content/tools.py`` registers each under this name, and the
    sub-agent specs pick their subsets by it. The values are the *short* names
    — the ``mcp__duct_content__`` prefix went with the Claude Agent SDK, whose
    MCP server was the thing that namespaced them. Keep in sync with the
    ``build_content_tools_lc`` registrations.
    """

    REMEMBER_FACT               = "RememberFact"
    SEARCH_MEMORY               = "SearchMemory"
    GET_MEMORY                  = "GetMemory"
    SUBMIT_PLAN                 = "submit_plan"
    SUBMIT_POST_DRAFT           = "submit_post_draft"
    EDIT_SLIDE                  = "edit_slide"
    FETCH_BRAND_CONTEXT         = "fetch_brand_context"
    FETCH_TOPIC_BANK            = "fetch_topic_bank"
    FETCH_FORMAT_LIBRARY        = "fetch_format_library"
    FETCH_AVATAR_LIBRARY        = "fetch_avatar_library"
    FETCH_CONTENT_HISTORY       = "fetch_content_history"
    FETCH_CONTENT_ASSETS        = "fetch_content_assets"
    FETCH_DISCOVERED_REFERENCES = "fetch_discovered_references"
    FETCH_POST                  = "fetch_post"
    FETCH_SLIDE_CONTEXT         = "fetch_slide_context"
    RENDER_SLIDE                = "render_slide"
    GENERATE_IMAGE              = "generate_image"
    EDIT_IMAGE                  = "edit_image"
    PUBLISH_POST                = "publish_post"
    MARK_POSTED                 = "mark_posted"
    LOG_METRICS                 = "log_metrics"


# Per-slide kind — drives which template renders the slide within a layout.
#   photo / text          — single image (or none) + overlay caption
#   collage               — 2×2 grid; one image per `items` cell
#   before-after          — do/don't split; two `items` cells (marker do/dont)
#   editorial             — single image on an ivory matte, serif typography
SlideKind = Literal["photo", "text", "collage", "before-after", "editorial"]

# Caption style keys — must match a `key` in agents/content/styles.py STYLES
# (plus "hook" for the slide-1 headline). The renderer maps these to classes.
CaptionStyle = Literal[
    "hook", "cap-stroke", "cap-pill", "cap-raw", "cap-whisper", "body-neutral"
]


class SlideItem(BaseModel):
    """One image cell inside a multi-image slide (collage grid cell, or one
    side of a before/after split). Each cell carries its own prompt + image,
    so cells are generated and go stale independently — same model as a Slide's
    own image. `image_prompt_used` anchors staleness."""

    model_config = ConfigDict(extra="ignore")

    label: str = ""                                # serif cell label / short caption
    marker: Literal["", "dont", "do"] = ""         # before-after: ❌ (dont) / ✅ (do)
    image_prompt: str = ""
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    image_asset_id: UUID | None = None
    image_url: str = ""
    image_prompt_used: str = ""

    def is_image_stale(self) -> bool:
        if not self.image_url:
            return False
        return (self.image_prompt or "").strip() != (self.image_prompt_used or "").strip()


class Slide(BaseModel):
    """One structured slide. The orchestrator authors copy + an image prompt;
    the image itself is filled in later (post-approval, one slide at a time).

    Staleness: `image_url` is bound to the `image_prompt_used` that produced
    it. When `image_prompt` later differs from `image_prompt_used` AND an
    image exists, the slide's image is out of date — see `is_image_stale`.
    Pure caption edits (overlay HTML text) never invalidate the image.
    """

    model_config = ConfigDict(extra="ignore")

    slide_id: str                                  # "slide-01"
    kind: SlideKind = "photo"
    role: str = ""                                 # hook | finding | reveal | bridge | cta | body
    caption_style: CaptionStyle = "cap-stroke"
    headline: str = ""                             # main caption / hook line
    subtext: str = ""                              # optional sub-line
    # Single-image slides (photo / text / editorial) use these fields directly.
    image_prompt: str = ""
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    image_asset_id: UUID | None = None             # set after generation
    image_url: str = ""                            # set after generation
    image_prompt_used: str = ""                    # prompt that produced image_url (staleness anchor)
    # Multi-image slides (collage / before-after) use cells instead. collage
    # aims for 4 cells; before-after uses 2 (first marker="dont", second "do").
    items: list[SlideItem] = Field(default_factory=list)

    def is_image_stale(self) -> bool:
        """True when a generated image no longer matches the current prompt."""
        if not self.image_url:
            return False
        return (self.image_prompt or "").strip() != (self.image_prompt_used or "").strip()


class PostDraft(BaseModel):
    """One draft post coming back from the draft_post sub-agent or orchestrator.

    `type` discriminator keeps PlanDraft and PostDraft distinguishable inside
    the <duct_artifact> tag.

    The orchestrator authors structured `slides` (copy + image prompts) and a
    `layout`; it does NOT write `slides_html`. submit_post_draft renders the
    HTML deterministically from `slides` via templates.py and derives the flat
    `image_prompts` list. `slides_html` is kept on the schema only so legacy
    callers / fallbacks still validate.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["post"] = "post"
    project_id: UUID
    post_dir_slug: str
    pillar: str
    topic: str
    topic_id: str | None = None
    post_type: Literal["slideshow", "video", "image"] = "slideshow"
    format_slug: str = ""   # which library format to build with (e.g. "format-d")
    layout: SlideLayout = SlideLayout.FULL_BLEED
    avatar_id: UUID | None = None
    slide_count: int = Field(default=7, ge=1, le=20)
    slides: list[Slide] = Field(default_factory=list)   # source of truth for content + images
    slides_html: str = ""                               # DERIVED by submit_post_draft (do not author)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    hook_type: str = ""
    hook_text: str = ""
    hook_emotion: str = ""              # frustration | shock | disbelief | anger | sadness
    save_cta: str = ""                  # slide-1 parenthetical naming a specific payoff slide
    tiktok_title: str = ""
    image_prompts: list[ImagePrompt] = Field(default_factory=list)
    audio_note: str | None = None
    bridge_text: str = ""               # slide-6 personal discovery bridge (first-person, "free app")
    strategic_note: str = ""           # 1-2 sentences: why this post works in the broader strategy
    visual_brief: str = ""              # reference-study output: lighting/posture/skin/gesture arc/copy voice
    emotional_arc: str = ""             # 5-slide energy arc, one line per slide
    camera_ref_pool: str = ""           # 'selfie-talking' | 'lifestyle' | 'closeup' — which ref pool to draw from
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
        agent_type="tiktok_studio",
        project_id=project_id,
        mode=mode,
        event_queue=asyncio.Queue(),
        chat_queue=asyncio.Queue(),
        steer_queue=asyncio.Queue(),
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
    "Slide",
    "SlideItem",
    "SlideLayout",
    "TopicCandidate",
    "TopicCandidates",
    "TrendSignal",
    "make_session",
]
