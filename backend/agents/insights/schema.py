"""Structured output schemas for the generate agent.

Uses extra='forbid' for OpenAI Structured Outputs compatibility.
These schemas are shared between the LangChain agent and the
Gemini synthesis path in service.google.brief.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class SynFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    type: SynFindingType
    title: str
    evidence: list[str] = Field(default_factory=list)
    impact: str = ""
    recommended_action: str = ""
    confidence: SynConfidenceLevel = SynConfidenceLevel.MEDIUM
    related_campaigns: list[str] = Field(default_factory=list)
    evidence_sources: list[SynEvidenceSource] = Field(default_factory=list)
    evidence_chain: SynEvidenceChain = Field(default_factory=SynEvidenceChain)


class SynRecommendedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    type: SynActionType
    title: str
    detail: str = ""
    priority: SynActionPriority = SynActionPriority.MEDIUM
    owner: str = "paid team"
    related_campaigns: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    evidence_sources: list[SynEvidenceSource] = Field(default_factory=list)


class SynNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: str
    summary: str
    operator_takeaway: str


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
