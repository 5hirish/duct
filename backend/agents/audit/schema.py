"""Pydantic schemas for the SEO Audit Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuditCategory(StrEnum):
    TECHNICAL = "technical_foundation"
    STRUCTURED_DATA = "structured_data"
    EEAT = "eeat_signals"
    GEO_AIO = "geo_aio"
    ON_PAGE = "on_page_seo"
    INTERNAL_LINKING = "internal_linking"
    BLOG_STRATEGY = "blog_content_strategy"
    OFF_PAGE = "off_page_authority"
    OPEN_GRAPH = "open_graph_social"


class Severity(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    OPPORTUNITY = "opportunity"


class AuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    category: AuditCategory
    severity: Severity
    title: str
    detail: str
    evidence: list[str] = Field(default_factory=list)
    affected_urls: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    effort: Literal["low", "medium", "high"] = "medium"
    impact: Literal["low", "medium", "high"] = "medium"


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


class CategorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: AuditCategory
    weight_pct: int = 0       # category's % weight in overall score (1–25)
    score: int = 0            # 0–100 for this category
    weighted_contribution: int = 0  # score × weight_pct / 100, rounded
    findings_count: int = 0
    fail_count: int = 0
    warn_count: int = 0
    pass_count: int = 0
    opportunity_count: int = 0


class AuditReport(BaseModel):
    """Top-level structured output from the synthesizer."""

    model_config = ConfigDict(extra="forbid")

    url: str
    generated_at: str
    update_label: str = ""
    overall_score: int = 0
    category_summaries: list[CategorySummary] = Field(default_factory=list)
    findings: list[AuditFinding] = Field(default_factory=list)
    executive_summary: str = ""
    top_priorities: list[str] = Field(default_factory=list)
    html_report: str = ""


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    business_context: AuditBusinessContext = Field(default_factory=AuditBusinessContext)
    engine: str = ""
    max_blog_posts: int = Field(default=5, ge=1, le=10)


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
    queue: object  # asyncio.Queue — typed as object to avoid import at module level
    answer_future: object | None  # asyncio.Future | None
    report_versions: list[VersionedReport] = field(default_factory=list)
