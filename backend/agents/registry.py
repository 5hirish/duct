"""Agent registry — canonical list of available agent types and their specs.

Each entry describes one agent type: its public identity (name, description,
capabilities) and the Pydantic model used to validate the POST /sessions body.

Adding a new agent type:
  1. Add a value to AgentType
  2. Add a value to AgentCapability if needed
  3. Define its config Pydantic model (can live anywhere; import here)
  4. Add an entry to AGENT_REGISTRY
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentType(StrEnum):
    SEO_AUDIT = "audit_seo"
    INSIGHTS = "insights"
    TIKTOK_STUDIO = "tiktok_studio"
    CONTENT_PLANNER = "content_planner"
    BLOG_WRITER = "blog-writer"     # future
    RESEARCH = "research"           # future


class AgentCapability(StrEnum):
    STREAMING = "streaming"                   # emits SSE events during run
    INTERACTIVE_QUESTIONS = "interactive_questions"  # uses AskUserQuestion mid-run
    VERSIONED_OUTPUT = "versioned_output"     # output evolves through report versions
    CHAT = "chat"                             # session stays alive for follow-up Q&A
    DATA_CONNECTORS = "data_connectors"       # requires OAuth data source connections
    FILE_UPLOAD = "file_upload"               # accepts image/file attachments in chat


class AgentSpec(BaseModel):
    """Public descriptor for one agent type — returned by GET /api/agents."""

    type: AgentType
    name: str
    description: str
    capabilities: list[AgentCapability]
    config_schema: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _seo_audit_spec() -> AgentSpec:
    from agents.audit.schema import AuditRequest
    return AgentSpec(
        type=AgentType.SEO_AUDIT,
        name="SEO Audit",
        description=(
            "Comprehensive organic growth audit. Crawls your site via its sitemap, "
            "analyses 9 SEO categories with Google-weighted scoring, and produces "
            "a standalone HTML report. Continues as an interactive chat session."
        ),
        capabilities=[
            AgentCapability.STREAMING,
            AgentCapability.INTERACTIVE_QUESTIONS,
            AgentCapability.VERSIONED_OUTPUT,
            AgentCapability.CHAT,
            AgentCapability.FILE_UPLOAD,
        ],
        config_schema=AuditRequest.model_json_schema(),
    )


def _insights_spec() -> AgentSpec:
    return AgentSpec(
        type=AgentType.INSIGHTS,
        name="Growth Insights",
        description=(
            "Paid ads and organic growth intelligence. Connects to Google Ads, GA4, "
            "and Search Console to synthesise a weekly brief with findings and "
            "recommended actions."
        ),
        capabilities=[
            AgentCapability.STREAMING,
            AgentCapability.DATA_CONNECTORS,
            AgentCapability.CHAT,
        ],
        active=True,
    )


def _blog_writer_spec() -> AgentSpec:
    return AgentSpec(
        type=AgentType.BLOG_WRITER,
        name="Blog Writer",
        description="SEO-optimised blog content generation. Coming soon.",
        capabilities=[
            AgentCapability.STREAMING,
            AgentCapability.INTERACTIVE_QUESTIONS,
            AgentCapability.CHAT,
        ],
        active=False,
    )


def _research_spec() -> AgentSpec:
    return AgentSpec(
        type=AgentType.RESEARCH,
        name="Research",
        description="Deep-dive research and competitive analysis. Coming soon.",
        capabilities=[
            AgentCapability.STREAMING,
            AgentCapability.INTERACTIVE_QUESTIONS,
            AgentCapability.CHAT,
            AgentCapability.FILE_UPLOAD,
        ],
        active=False,
    )


def _tiktok_studio_spec() -> AgentSpec:
    """Spec for the Content Studio agent (draft_post + clone_post).

    Session lifecycle runs through the unified /api/agents/tiktok_studio/*
    endpoints (create → stream → messages). The content-specific CRUD and
    slide-render routes still live under /api/content/*.
    """
    from agents.content.schema import DraftPostRequest
    return AgentSpec(
        type=AgentType.TIKTOK_STUDIO,
        name="Content Studio",
        description=(
            "Post drafts for TikTok-style carousels. Drafts captions and slides, "
            "generates images, and publishes via PostBridge. (Content planning "
            "now lives in the Content Planner agent.)"
        ),
        capabilities=[
            AgentCapability.STREAMING,
            AgentCapability.INTERACTIVE_QUESTIONS,
            AgentCapability.VERSIONED_OUTPUT,
            AgentCapability.CHAT,
            AgentCapability.FILE_UPLOAD,
        ],
        config_schema=DraftPostRequest.model_json_schema(),
        active=True,
    )


def _content_planner_spec() -> AgentSpec:
    """Spec for the Content Planner agent — the strategist that owns the
    project's canonical rolling 7-day plan (research → best times → sequencing
    → narrative). Runs through /api/agents/content_planner/* (mode=update_plan)."""
    from agents.planner.schema import PlannerRequest
    return AgentSpec(
        type=AgentType.CONTENT_PLANNER,
        name="Content Planner",
        description=(
            "A research-heavy content strategist. Researches platform trends and "
            "competitors, reviews past-post performance, picks the best post "
            "times per platform and geography, sequences content types into a "
            "long-term narrative, and (re)writes the project's canonical 7-day plan."
        ),
        capabilities=[
            AgentCapability.STREAMING,
            AgentCapability.INTERACTIVE_QUESTIONS,
            AgentCapability.CHAT,
        ],
        config_schema=PlannerRequest.model_json_schema(),
        active=True,
    )


# Populated at import time — add new agents here
AGENT_REGISTRY: dict[str, AgentSpec] = {
    AgentType.SEO_AUDIT:         _seo_audit_spec(),
    AgentType.INSIGHTS:          _insights_spec(),
    AgentType.TIKTOK_STUDIO:     _tiktok_studio_spec(),
    AgentType.CONTENT_PLANNER:   _content_planner_spec(),
    AgentType.BLOG_WRITER:       _blog_writer_spec(),
    AgentType.RESEARCH:          _research_spec(),
}


def get_spec(agent_type: str) -> AgentSpec | None:
    return AGENT_REGISTRY.get(agent_type)


def list_specs(active_only: bool = False) -> list[AgentSpec]:
    specs = list(AGENT_REGISTRY.values())
    if active_only:
        specs = [s for s in specs if s.active]
    return specs
