"""Pydantic schemas + dataclasses for the Content Studio agent.

Two groups:
  - Domain shapes — ported from nomadapps/marketing/app/src/types.ts
    (Character, Day, Avatar, AppContext → ContentBrandContext). A post's
    ``perf`` has no schema here: its keys are service/content_metrics.py's.
  - Wire shapes — request/session models the route layer uses.
  - Sub-agent output schemas — TopicCandidates, PostDraft, PlanDraft.
    Used inside writer @tools to validate JSON the orchestrator passes in.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.core.session import BaseAgentSession

from agents.content.channels import Platform
from agents.models import AspectRatio, ImageModel, Provider


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
    # A TikTok post to model the draft on (issue #222). Stored canonical, so
    # the runner and the session only ever see a URL rebuilt from a parsed
    # handle and post id; anything else is a 422 before a session starts.
    clone_url: str | None = None

    @field_validator("clone_url")
    @classmethod
    def _clone_url_is_one_tiktok_post(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        from service.clone_reference import parse_tiktok_post_url

        return parse_tiktok_post_url(value).url


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
    # What this run may spend on images — a *different* provider from the one
    # driving the conversation, so it is resolved separately and can be absent
    # while the run itself is fine (the image tools then decline). Empty is not
    # "use the server's": the resolver already decided that, and the tools must
    # never reach past it to config. See routes/content.py::_attach_image_run
    # and agents/engines.resolve_image_run.
    image_provider: Provider | None = None
    image_api_key: str = ""
    # The Gemini key, when the image run resolved to Google: it also backs
    # Duct's own WebSearch on providers with no usable built-in. Empty on any
    # other image provider, so a run on an OpenAI key gets OpenAI pictures and
    # no Gemini-grounded search — the same as before images went multi-provider.
    gemini_api_key: str = ""
    # A clone run's link to its reference — asset id, URL, author, why it
    # worked — set by the runner before the opening turn. submit_post_draft
    # writes it onto the post as `clone_source` with the model's verdict, so
    # the model never types an id it could get wrong.
    clone_reference: dict | None = None


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
    # Why the research pass did not contribute, when it did not. Shown on the
    # enrichment step and logged; not rendered into the prompt.
    degraded_reason:          str = ""


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
    SUBMIT_ASSESSMENT           = "submit_assessment"
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
    # before-after: ❌ (dont) / ✅ (do); "" everywhere else. A plain str with a
    # validator rather than Literal["", "dont", "do"]: the writers expose this
    # model as their argument schema and Gemini rejects an enum with an empty
    # member ("enum[0]: cannot be empty", 400) — the whole tool set with it.
    marker: str = Field("", description='"dont" or "do" on a before-after cell; "" otherwise.')

    @field_validator("marker")
    @classmethod
    def _marker_is_known(cls, value: str) -> str:
        if value not in ("", "dont", "do"):
            raise ValueError('marker must be "dont", "do" or ""')
        return value
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


# ---------------------------------------------------------------------------
# Cloning a reference (issue #222)
# ---------------------------------------------------------------------------


class CloneFit(StrEnum):
    """Whether the reference's subject already lives in one of the pillars."""

    IN_NICHE     = "in_niche"
    OUT_OF_NICHE = "out_of_niche"


class CloneProof(StrEnum):
    """Whether the reference clearly outperformed."""

    PROVEN = "proven"
    WEAK   = "weak"


class CloneApproach(StrEnum):
    """How closely a clone copies its reference — FIT × PROOF, decided here.

    Derived rather than asked for, so the recorded approach cannot disagree
    with the verdict it came from. Mirrored in app/src/lib/contentEnums.js.
    """

    CLOSE          = "close"           # in niche and proven: a recipe, copy it tightly
    ADAPT          = "adapt"           # in niche, weak proof: keep the structure, fix the rest
    STRUCTURE_ONLY = "structure_only"  # out of niche: borrow the format, rebuild the substance


def clone_approach(fit: CloneFit, proof: CloneProof) -> CloneApproach:
    if fit is CloneFit.OUT_OF_NICHE:
        return CloneApproach.STRUCTURE_ONLY
    return CloneApproach.CLOSE if proof is CloneProof.PROVEN else CloneApproach.ADAPT


class CloneVerdict(BaseModel):
    """The clone's own call, carried on the PostDraft of a clone run."""

    model_config = ConfigDict(extra="forbid")

    fit: CloneFit = Field(description="in_niche when the reference's subject is one of the brand's pillars.")
    proof: CloneProof = Field(description="proven when the reference clearly outperformed for its creator's size.")
    kept: str = Field(description="Which elements of the reference you kept, and why — one or two sentences.")


def clone_source(link: dict | None, verdict: CloneVerdict | None) -> dict | None:
    """What a cloned post records about its reference, or None for any other post.

    ``link`` is the server's half (reference id, URL, author, why it worked):
    the session's on the first write, the row's own on a later one, so a
    refinement in a resumed conversation keeps the link and updates the call.
    """
    if not link:
        return None
    record = dict(link)
    if verdict is not None:
        record.update(
            fit=verdict.fit.value,
            proof=verdict.proof.value,
            approach=clone_approach(verdict.fit, verdict.proof).value,
            kept=verdict.kept.strip(),
        )
    return record


class ReferenceDiagnosis(BaseModel):
    """Why a reference worked, read by the run's own model before the clone.

    One structured call (agents/content/v1/runner.py); the kickoff turn
    carries the result as text, and ``why_it_worked`` is what the post keeps.
    Every field has a default, as ``DraftInference`` does: a provider that
    leaves one out still returns the rest, which beats no diagnosis at all.
    """

    model_config = ConfigDict(extra="ignore")

    hook: str = Field("", description="What stops the scroll in the first second, and the mechanism behind it.")
    structure: str = Field("", description="How each slide or beat pulls to the next; where the payoff and the save-worthy moment sit.")
    on_screen_text: list[str] = Field(
        default_factory=list,
        description="The text on each slide, verbatim and in order. Empty when you cannot see the slides.",
    )
    lever: str = Field("", description="The one signal it won on: saves, shares, comments, completion or reach.")
    why_it_worked: str = Field("", description="Two or three sentences naming the specific element that drove the result.")
    audience: str = Field("", description="Who this was for: the viewer it won, as specifically as the post shows.")
    creator: str = Field("", description="Who is on screen (approximate age, look, energy), or empty when nobody is.")


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
    clone: CloneVerdict | None = Field(
        None, description="Clone runs only: your FIT × PROOF call and what you kept. Omit otherwise.",
    )


class PlanDraft(BaseModel):
    """What submit_plan accepts — and the argument schema the model is shown.

    ``Day`` itself stays lenient because stored rows are read back through
    it; the strictness lives here, at the boundary the model writes across.
    A model probing the tool to learn its shape once persisted ``days: [{}]``
    as a real plan, which then counted as the deliverable.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["plan"] = "plan"
    project_id: UUID
    name: str = ""
    start_date: date | None = None
    character: Character = Field(default_factory=Character)
    days: list[Day] = Field(min_length=1, description="The posts, in order; each needs a topic and a pillar.")

    @field_validator("days")
    @classmethod
    def _every_day_is_planned(cls, days: list[Day]) -> list[Day]:
        unplanned = [i for i, d in enumerate(days) if not d.topic.strip() or not d.pillar.strip()]
        if unplanned:
            raise ValueError(f"every day needs a non-empty topic and pillar; days at index {unplanned} do not")
        return days


# ---------------------------------------------------------------------------
# Pre-publish review — deterministic checks plus six markers the reviewer
# scores. The scoring math and the marker weights are in
# agents/content/assessment.py. Every id below crosses the wire: the app words
# them (app/src/lib/contentReview.js), so the backend sends ids, never labels.
# ---------------------------------------------------------------------------


class ReviewMarker(StrEnum):
    """The six signals a carousel's reach turns on, as the reviewer scores them."""

    HOOK_STRENGTH          = "hook_strength"
    NARRATIVE_MOMENTUM     = "narrative_momentum"
    SAVE_WORTHINESS        = "save_worthiness"
    SHAREABILITY_RESONANCE = "shareability_resonance"
    VISUAL_QUALITY         = "visual_quality"
    CTA_CAPTION_FIT        = "cta_caption_fit"


class SanityCheckId(StrEnum):
    """One deterministic check each, and one way for each to fail — which is
    why the caption and the hashtags are two checks apiece: the app can say
    what is wrong from the id alone."""

    SLIDES_HAVE_IMAGES    = "slides_have_images"
    IMAGES_FRESH          = "images_fresh"
    SLIDES_HAVE_HEADLINES = "slides_have_headlines"
    CAPTION_PRESENT       = "caption_present"
    CAPTION_LENGTH        = "caption_length"
    NO_PLACEHOLDER_TEXT   = "no_placeholder_text"
    HASHTAGS_PRESENT      = "hashtags_present"
    HASHTAGS_UNIQUE       = "hashtags_unique"


class CheckSeverity(StrEnum):
    """How much a failure costs the overall: HARD ships a broken post (a slide
    with no image, no caption), SOFT ships a weaker one (no hashtags)."""

    HARD = "hard"
    SOFT = "soft"


class ReviewBand(StrEnum):
    STRONG     = "strong"
    GOOD       = "good"
    NEEDS_WORK = "needs_work"
    NOT_READY  = "not_ready"


class MarkerScore(BaseModel):
    """One marker as the reviewer scores it — and everything it may say.

    There is no weight here on purpose: this is the argument schema of
    submit_assessment, so a model cannot send one, and an extra key is dropped
    rather than trusted. The server stamps the weight (``ContentMarker``).
    """

    model_config = ConfigDict(extra="ignore")

    id: ReviewMarker
    score: int = Field(ge=0, le=100, description="0-100. 90+ exceptional, 70-89 strong, 50-69 mixed, 30-49 weak, below 30 broken.")
    verdict: str = Field("", description="One line: the judgement.")
    why: str = Field("", description="The evidence, naming slides.")
    fix: str = Field("", description="The single most valuable concrete change.")


class ContentMarker(MarkerScore):
    """A scored marker with the weight the server gave it."""

    weight: float = 0.0


class SanityCheck(BaseModel):
    """One deterministic check. Advisory: a failure is shown and costs points;
    it never disables Publish. ``offenders`` names what failed — slide ids,
    ``caption``, or the repeated hashtags — so the fix can be pointed at."""

    model_config = ConfigDict(extra="ignore")

    id: SanityCheckId
    passed: bool
    severity: CheckSeverity = CheckSeverity.HARD
    offenders: list[str] = Field(default_factory=list)


class PublishAssessment(BaseModel):
    """A post's pre-publish review. Stored whole in ``content_posts.last_assessment``
    when the agent scores it; served re-read against the post as it is now
    (``assessment.reassess``), so the checks are always current.

    ``overall`` / ``content_score`` / ``band`` are None until the post has been
    scored. ``stale`` is true when the post changed after the markers were
    scored — the checks cannot be stale, the reviewer's judgement can.
    """

    model_config = ConfigDict(extra="ignore")

    overall: int | None = None
    content_score: int | None = None
    band: ReviewBand | None = None
    markers: list[ContentMarker] = Field(default_factory=list)
    checks: list[SanityCheck] = Field(default_factory=list)
    notes: str = ""
    scored_at: str = ""
    # Digest of the slides, caption and hashtags that were scored.
    fingerprint: str = ""
    stale: bool = False


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
    "CheckSeverity",
    "CloneApproach",
    "CloneFit",
    "CloneProof",
    "CloneVerdict",
    "ContentAnswerRequest",
    "ContentBrandContext",
    "ContentChatMessage",
    "ContentMarker",
    "ContentPillar",
    "ContentResearchContext",
    "ContentSession",
    "ContentVisualAssets",
    "Day",
    "DraftPostRequest",
    "ImagePrompt",
    "MarkerScore",
    "PillarHistorySignal",
    "PlanDraft",
    "PlanRequest",
    "PostDraft",
    "PublishAssessment",
    "ReferenceDiagnosis",
    "ReviewBand",
    "ReviewMarker",
    "RunMode",
    "SanityCheck",
    "SanityCheckId",
    "Slide",
    "SlideItem",
    "SlideLayout",
    "TopicCandidate",
    "TopicCandidates",
    "TrendSignal",
    "clone_approach",
    "clone_source",
    "make_session",
]
