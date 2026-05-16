"""Pydantic schemas for the SEO Audit Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.models import AgentEffort
from agents.user_preferences import UserPreferences




class PageSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    page_type: Literal["landing_page", "blog_post", "other"] = "other"
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


class AuditBusinessContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_name: str = ""
    business_description: str = ""
    business_goals: str = ""
    target_keywords: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    primary_content_type: Literal["blog", "landing_pages", "product_pages", "docs", ""] = ""


class AuditReport(BaseModel):
    """Artifact-pattern audit report: the HTML document IS the report.

    The model generates a full self-contained HTML document and streams it
    inside <duct_report> tags. No JSON schema enforcement — the model writes
    whatever it judges appropriate for the site.
    """

    url: str
    generated_at: str
    update_label: str = ""
    executive_summary: str = ""   # text the model streamed before the HTML tag
    html_report: str = ""         # full self-contained HTML document


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


@dataclass
class AuditSession:
    session_id: str
    agent_type: str                       # e.g. "audit_seo"
    event_queue: object                   # asyncio.Queue — agent → SSE consumer
    chat_queue: object                    # asyncio.Queue — user messages → agent
    answer_future: object | None          # asyncio.Future | None — for AskUserQuestion
    created_at: float = 0.0              # time.monotonic() at creation
    report_versions: list[VersionedReport] = field(default_factory=list)
