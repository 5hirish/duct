"""Pydantic schemas for the SEO Audit Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agents.core.business_context import BusinessContext
from agents.core.session import BaseAgentSession
from agents.models import AgentEffort
from agents.user_preferences import UserPreferences


# ---------------------------------------------------------------------------
# Enums — replace all Literal[...] string constants
# ---------------------------------------------------------------------------

class Severity(StrEnum):
    fail        = "fail"
    warn        = "warn"
    pass_       = "pass"        # "pass" is a Python keyword; value stays "pass" for JSON
    opportunity = "opportunity"


class ImpactLevel(StrEnum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"


class EffortLevel(StrEnum):
    low    = "low"
    medium = "medium"
    high   = "high"


class EffortEstimate(StrEnum):
    under_1hr     = "under_1hr"
    two_to_4hrs   = "2_to_4hrs"
    one_to_3_days = "1_to_3_days"
    one_to_2_wks  = "1_to_2_wks"
    ongoing       = "ongoing"


class ScoreBand(StrEnum):
    healthy    = "healthy"
    good       = "good"
    needs_work = "needs_work"
    critical   = "critical"


class PageType(StrEnum):
    landing_page = "landing_page"
    blog_post    = "blog_post"
    other        = "other"


class ContentType(StrEnum):
    unset         = ""              # not specified
    blog          = "blog"
    landing_pages = "landing_pages"
    product_pages = "product_pages"
    docs          = "docs"


class ReportMode(StrEnum):
    freehand = "freehand"
    template = "template"


# ---------------------------------------------------------------------------
# Crawl schemas
# ---------------------------------------------------------------------------

class PageSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    page_type: PageType = PageType.other
    http_status: int = 200

    # <head> signals
    title: str = ""
    meta_description: str = ""
    canonical: str = ""
    is_noindex: bool = False
    hreflang_langs: list[str] = Field(default_factory=list)   # e.g. ["en", "es", "x-default"]

    # Heading structure
    h1s: list[str] = Field(default_factory=list)
    h2s: list[str] = Field(default_factory=list)

    # Images
    image_count: int = 0
    images_missing_alt: int = 0

    # Structured data
    has_schema_org: bool = False
    schema_types: list[str] = Field(default_factory=list)

    # Open Graph + social
    og_title: str = ""
    og_description: str = ""
    og_image: str = ""
    og_type: str = ""                                          # "website" | "article" | …
    twitter_card: str = ""
    twitter_image: str = ""

    # Content
    word_count_approx: int = 0
    body_text_snippet: str = ""                                # first 500 chars; useful for E-E-A-T analysis

    # Links — internal_links[i] and internal_link_anchors[i] are parallel arrays
    internal_links: list[str] = Field(default_factory=list)
    internal_link_anchors: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)
    external_link_anchors: list[str] = Field(default_factory=list)

    # From sitemap
    lastmod: str = ""

    # HTTP-level signals (from response headers — invisible to HTML-only parsers)
    x_robots_tag: str = ""          # X-Robots-Tag header; same authority as <meta name="robots">
    vary_header: str = ""           # Vary: User-Agent → server serving different content per bot
    cache_control: str = ""         # Cache-Control header; freshness signal for recrawl scheduling

    # Technical crawl signals
    ttfb_ms: float = 0.0            # time to first byte in milliseconds
    redirect_chain: list[dict] = Field(default_factory=list)  # [{"url": "...", "status": 301}, ...]

    # Rendering / SPA signals
    is_spa_suspected: bool = False   # likely client-side rendered (empty body + known SPA markers)
    spa_framework: str = ""          # detected framework: "next_ssr", "next_csr", "react_csr", "gatsby", "nuxt", ""
    noscript_content: str = ""       # text visible inside <noscript> — what non-JS crawlers fall back to

    # Supplemental page signals
    amp_url: str = ""                # <link rel="amphtml" href="..."> URL
    preload_hints: int = 0           # count of <link rel="preload"> — performance signal
    schema_json_ld: list[dict] = Field(default_factory=list)   # full JSON-LD objects (not just @types)
    microdata_types: list[str] = Field(default_factory=list)   # schema types found via microdata


class CrawlPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_url: str
    sitemap_url: str = ""
    robots_txt_url: str = ""
    llms_txt_url: str = ""
    landing_pages: list[str] = Field(default_factory=list)
    blog_posts: list[str] = Field(default_factory=list)
    total_sitemap_urls: int = 0


class CrawlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: CrawlPlan
    robots_txt: str = ""
    llms_txt: str = ""
    pages: list[PageSignals] = Field(default_factory=list)
    sitemap_errors: list[str] = Field(default_factory=list)
    crawl_errors: list[str] = Field(default_factory=list)


# Business context is now the shared, unified model passed equally to every
# agent (agents/core/business_context.py) — a superset of every agent's fields
# with extra="ignore", so existing audit payloads validate unchanged.
# AuditBusinessContext is kept as an alias for backwards-compatible imports.
AuditBusinessContext = BusinessContext


# ---------------------------------------------------------------------------
# Context enrichment (pre-synthesis research sub-agent output)
# ---------------------------------------------------------------------------

class CompetitorSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    positioning: str = ""          # value prop / target audience claim
    content_pillars: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)  # vs the target site


class AuditResearchContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_content_pillars: list[str] = Field(default_factory=list)
    brand_schema_types: list[str] = Field(default_factory=list)
    competitors: list[CompetitorSignals] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)   # topics competitors cover, target doesn't
    enrichment_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Audit findings
# ---------------------------------------------------------------------------

class AffectedUrl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    issue_value: str   # e.g. "13 chars", "HTTP 404", "0 words found"


class AuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                                                    # slug, e.g. "title-too-short"
    severity: Severity
    title: str
    description: Annotated[str, Field(max_length=250)]         # 1 sentence — what's happening and why it matters
    tooltip: str                                               # 1 sentence for non-SEO users (hover text)
    affected_urls: list[AffectedUrl] = Field(default_factory=list)
    recommendation: Annotated[str, Field(max_length=200)] = "" # 1 imperative sentence starting with a verb
    impact: ImpactLevel = ImpactLevel.medium
    effort: EffortLevel = EffortLevel.medium


class AuditCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                # "on_page_seo", "technical_foundation", etc.
    label: str
    score: int             # 0–100, computed by agent from scoring rules
    tooltip: str           # plain-English: what this category measures and why it matters
    fail_count: int = 0
    warn_count: int = 0
    pass_count: int = 0
    opp_count: int = 0
    findings: list[AuditFinding] = Field(default_factory=list)


class AuditPriority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    title: str
    why_it_matters: Annotated[str, Field(max_length=180)]  # 1 sentence — business impact only
    severity: Severity
    affected_url_count: int = 0
    category_id: str
    finding_id: str        # cross-reference into a category finding


class RoadmapTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str
    effort_estimate: EffortEstimate = EffortEstimate.one_to_3_days
    note: str = ""   # optional override / exception note


class RoadmapPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str       # e.g. "0–30 days"
    theme: str       # e.g. "Unblock"
    tasks: list[RoadmapTask] = Field(default_factory=list)


class CrawlSummary(BaseModel):
    """Aggregate crawl-level stats for frontend callout cards."""
    model_config = ConfigDict(extra="forbid")

    avg_ttfb_ms: float = 0.0
    pages_with_redirects: int = 0
    spa_pages_count: int = 0
    pages_noindex: int = 0
    pages_missing_title: int = 0
    pages_missing_h1: int = 0


class StructuredAuditData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    generated_at: str
    overall_score: int                # weighted average computed from scoring rules
    score_band: ScoreBand
    pages_crawled: int                # UI uses this to compute coverage callout
    total_sitemap_urls: int
    key_signals: list[str] = Field(default_factory=list)  # exactly 3 short strings — coach's brief
    total_issues: int = 0
    total_warnings: int = 0
    total_opportunities: int = 0
    crawl_summary: CrawlSummary | None = None
    categories: list[AuditCategory] = Field(default_factory=list)  # all 9, sorted by weight desc
    top_priorities: list[AuditPriority] = Field(default_factory=list)
    headline: str = ""                                    # 10–15 word punchy verdict hook
    wins: list[str] = Field(default_factory=list)         # 3–5 noun phrases of what's working
    roadmap: list[RoadmapPhase] = Field(default_factory=list)
    strategic_narrative: str = ""                         # free-text competitive landscape + content opportunity analysis


# ---------------------------------------------------------------------------
# Report + session containers
# ---------------------------------------------------------------------------

class AuditReport(BaseModel):
    """Audit report — either freehand HTML (streaming tag-parsed) or structured template data.

    freehand mode: html_report is a complete self-contained HTML document generated by the
    model inside <duct_report> tags. structured_data is None.

    template mode: structured_data is a StructuredAuditData populated via the SubmitAuditReport
    MCP tool call. html_report is empty — the frontend template renders the data visually.
    """

    url: str
    generated_at: str
    update_label: str = ""
    executive_summary: str = ""
    report_mode: ReportMode = ReportMode.freehand
    template_id: str = ""
    html_report: str = ""                               # freehand only
    structured_data: StructuredAuditData | None = None  # template only


class CrawlDepth(StrEnum):
    """Controls how many pages the crawler fetches before synthesis.

    LIGHT  — top 5 pages or 20% of sitemap URLs, whichever is smaller (max 15).
             Good for quick checks and tests.
    DEEP   — up to 30 landing pages + 5 blog posts (existing default).
    """
    LIGHT = "light"
    DEEP  = "deep"


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    business_context: AuditBusinessContext = Field(default_factory=AuditBusinessContext)
    engine: str = ""
    max_blog_posts: int = Field(default=5, ge=1, le=10)
    effort: AgentEffort = AgentEffort.MEDIUM
    adaptive_thinking: bool = False
    crawl_depth: CrawlDepth = CrawlDepth.DEEP
    user_preferences: UserPreferences = Field(default_factory=UserPreferences)
    report_mode: ReportMode = ReportMode.freehand
    template_id: str = "seo_v1"


class AuditAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str]


class AuditChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | list
    context_version_id: int | None = None


@dataclass
class VersionedReport:
    version_id: int
    label: str
    report: AuditReport
    created_at: str


@dataclass(kw_only=True)
class AuditSession(BaseAgentSession):
    """Audit session — BaseAgentSession (session_id, agent_type, queues,
    answer_future, created_at, pipeline_task) plus report versioning."""

    report_versions: list[VersionedReport] = field(default_factory=list)
    report_mode: str = "freehand"
    template_id: str = ""
