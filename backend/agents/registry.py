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


# Populated at import time — add new agents here
AGENT_REGISTRY: dict[str, AgentSpec] = {
    AgentType.SEO_AUDIT: _seo_audit_spec(),
    AgentType.INSIGHTS:  _insights_spec(),
    AgentType.BLOG_WRITER: _blog_writer_spec(),
    AgentType.RESEARCH:  _research_spec(),
}


def get_spec(agent_type: str) -> AgentSpec | None:
    return AGENT_REGISTRY.get(agent_type)


def list_specs(active_only: bool = False) -> list[AgentSpec]:
    specs = list(AGENT_REGISTRY.values())
    if active_only:
        specs = [s for s in specs if s.active]
    return specs
