"""Structured output schemas for the insights agent, plus its session shapes.

The ``Syn*`` / ``SynthesisSchema`` half is the structured output of the legacy
two-call pipeline (since deleted), still used by the
non-interactive brief path. ``extra='forbid'`` throughout for OpenAI Structured
Outputs compatibility; also shared with the Gemini synthesis path in
``service/google/brief.py``.

``InsightsRequest`` / ``InsightsSession`` at the bottom belong to the autonomous
session agent (``agents/insights/v1/runner.py``) and mirror audit's
``AuditRequest`` / ``AuditSession``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agents.core.artifacts import Finding, Narrative, RecommendedAction
from agents.core.context import BusinessContext
from agents.core.session import BaseAgentSession, register_session
from agents.preferences import UserPreferences
from agents.insights.entities import (
    SynActionPriority,
    SynActionType,
    SynConfidenceLevel,
    SynDataSource,
    SynEntityType,
    SynFindingType,
)


class SynEvidenceChain(BaseModel):
    """Multi-source evidence linking supplementary data to a finding."""

    model_config = ConfigDict(extra="forbid")

    primary_metric: str = ""
    contributing_factors: list[str] = Field(default_factory=list)
    data_sources_used: list[str] = Field(default_factory=list)


class SynClassificationOverride(BaseModel):
    """LLM override of a deterministic campaign classification."""

    model_config = ConfigDict(extra="forbid")

    campaign_name: str
    baseline_action: str
    override_action: str
    reasoning: str


class SynEvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SynDataSource = SynDataSource.GOOGLE_ADS
    entity_type: SynEntityType = SynEntityType.CAMPAIGN
    entity_name: str = ""
    metric: str = ""
    note: str = ""
    connector_entity_id: str = ""


class SynFinding(Finding):
    """Insights finding — extends the shared Finding base (id, title, impact,
    evidence, evidence_sources) with paid/organic-specific fields."""

    model_config = ConfigDict(extra="forbid")

    type: SynFindingType
    recommended_action: str = ""
    confidence: SynConfidenceLevel = SynConfidenceLevel.MEDIUM
    related_campaigns: list[str] = Field(default_factory=list)
    evidence_sources: list[SynEvidenceSource] = Field(default_factory=list)
    evidence_chain: SynEvidenceChain = Field(default_factory=SynEvidenceChain)


class SynRecommendedAction(RecommendedAction):
    """Insights action — extends the shared RecommendedAction base (id, title,
    detail, evidence) with paid/organic-specific fields."""

    model_config = ConfigDict(extra="forbid")

    type: SynActionType
    priority: SynActionPriority = SynActionPriority.MEDIUM
    owner: str = "paid team"
    related_campaigns: list[str] = Field(default_factory=list)
    evidence_sources: list[SynEvidenceSource] = Field(default_factory=list)


class SynNarrative(Narrative):
    """Insights narrative — the shared Narrative (verdict / summary / takeaway)."""

    model_config = ConfigDict(extra="forbid")


class BlockThreshold(BaseModel):
    """Optional visual threshold metadata for block rendering hints."""

    model_config = ConfigDict(extra="forbid")

    field: str = ""
    below: float | None = None
    above: float | None = None
    tone: str = ""


class BlockSpec(BaseModel):
    """One dashboard block emitted by synthesis."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    block_type: Literal[
        "kpi_strip",
        "bar_chart",
        "time_series",
        "scatter",
        "table",
        "heatmap",
        "signal_list",
        "action_list",
        "narrative",
        "pie_chart",
    ]
    title: str
    data_source: str
    x_field: str = ""
    y_field: str = ""
    group_by: str = ""
    sort_by: str = ""
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = 0
    highlight_threshold: BlockThreshold = Field(default_factory=BlockThreshold)
    insight_note: str = ""
    kpi_fields: list[str] = Field(default_factory=list)


class DashboardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks: list[BlockSpec] = Field(default_factory=list)


class SynthesisSchema(BaseModel):
    """Top-level structured output for the generate agent synthesis phase."""

    model_config = ConfigDict(extra="forbid")

    narrative: SynNarrative
    highlights: list[SynFinding] = Field(default_factory=list)
    risks: list[SynFinding] = Field(default_factory=list)
    recommended_actions: list[SynRecommendedAction] = Field(default_factory=list)
    classification_overrides: list[SynClassificationOverride] = Field(default_factory=list)
    analysis_notes: str = ""
    dashboard_spec: DashboardSpec = Field(default_factory=DashboardSpec)


# ---------------------------------------------------------------------------
# Autonomous session agent — request + session shapes
# ---------------------------------------------------------------------------


class InsightsRequest(BaseModel):
    """Body of ``POST /api/agents/insights/sessions``.

    Deliberately almost empty. The old pipeline required the caller to have
    already decided the connectors, the account/property/site for each, the goal
    and the date range; the agent now discovers or asks for all of it. What
    remains is a project to work in and, optionally, a sentence about what the
    user wants.
    """

    model_config = ConfigDict(extra="forbid")

    # Local-only projects have non-UUID ids, so this stays a string and is
    # parsed defensively — same as AuditRequest.
    project_id: str | None = None
    prompt: str = ""

    # Persisted-conversation controls (same semantics as audit and content).
    conversation_id: str | None = None
    resume: bool = False
    start_fresh: bool = False

    business_context: BusinessContext = Field(default_factory=BusinessContext)
    user_preferences: UserPreferences = Field(default_factory=UserPreferences)
    engine: str = ""

    # Optional steer, not a mode switch: it selects which knowledge packs and
    # protocol text to prefer when the intent is already obvious from the
    # request. Empty means the agent decides.
    focus: Literal["", "paid_ads", "organic_growth"] = ""

    # False = "don't remember this session": no memory digest is injected, the
    # memory tools are not mounted, and nothing is consolidated on close.
    remember: bool = True


@dataclass(kw_only=True)
class InsightsSession(BaseAgentSession):
    """Insights session — ``BaseAgentSession`` plus what the runner and the
    route stamp on it.

    Declared rather than assigned ad hoc (the way audit grew) so the contract
    between ``routes/agents.py`` and the runner is readable in one place.
    """

    # Stamped by routes/agents.py at creation.
    user_id: UUID | None = None
    conversation_id: UUID | None = None
    recorder: Any = None
    resume: bool = False

    # Set only after membership is verified — the memory tools key off this, so
    # a value here means "the caller provably belongs to this project".
    artifact_project_id: UUID | None = None
    # True when the user asked not to be remembered: no digest, no memory tools,
    # no consolidation on close.
    memory_off: bool = False


def create_insights_session(session_id: str, agent_type: str = "insights") -> InsightsSession:
    """Create and register an insights session with both queues.

    Called before the pipeline starts so the SSE stream endpoint can attach to
    ``event_queue`` independently of when the agent begins work.
    """
    return register_session(
        InsightsSession(
            session_id=session_id,
            agent_type=agent_type,
            event_queue=asyncio.Queue(),  # agent → SSE consumer
            chat_queue=asyncio.Queue(),   # user messages → agent
            answer_future=None,
        )
    )
