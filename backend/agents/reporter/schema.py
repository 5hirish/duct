"""Structured output schemas for the generate agent.

Uses extra='forbid' for OpenAI Structured Outputs compatibility.
These schemas are shared between the LangChain agent and the legacy
Gemini synthesis path in service.google.brief.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from agents.reporter.entities import (
    SynActionPriority,
    SynActionType,
    SynConfidenceLevel,
    SynDataSource,
    SynEntityType,
    SynFindingType,
)


class SynEvidenceChain(BaseModel, extra="forbid"):
    """Multi-source evidence linking supplementary data to a finding."""

    primary_metric: str = ""
    contributing_factors: List[str] = Field(default_factory=list)
    data_sources_used: List[str] = Field(default_factory=list)


class SynClassificationOverride(BaseModel, extra="forbid"):
    """LLM override of a deterministic campaign classification."""

    campaign_name: str
    baseline_action: str
    override_action: str
    reasoning: str


class SynEvidenceSource(BaseModel, extra="forbid"):
    source: SynDataSource = SynDataSource.GOOGLE_ADS
    entity_type: SynEntityType = SynEntityType.CAMPAIGN
    entity_name: str = ""
    metric: str = ""
    note: str = ""
    connector_entity_id: str = ""


class SynFinding(BaseModel, extra="forbid"):
    finding_id: str
    type: SynFindingType
    title: str
    evidence: List[str] = Field(default_factory=list)
    impact: str = ""
    recommended_action: str = ""
    confidence: SynConfidenceLevel = SynConfidenceLevel.MEDIUM
    related_campaigns: List[str] = Field(default_factory=list)
    evidence_sources: List[SynEvidenceSource] = Field(default_factory=list)
    evidence_chain: SynEvidenceChain = Field(default_factory=SynEvidenceChain)


class SynRecommendedAction(BaseModel, extra="forbid"):
    action_id: str
    type: SynActionType
    title: str
    detail: str = ""
    priority: SynActionPriority = SynActionPriority.MEDIUM
    owner: str = "paid team"
    related_campaigns: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    evidence_sources: List[SynEvidenceSource] = Field(default_factory=list)


class SynNarrative(BaseModel, extra="forbid"):
    verdict: str
    summary: str
    operator_takeaway: str


class SynthesisSchema(BaseModel, extra="forbid"):
    """Top-level structured output for the generate agent synthesis phase."""

    narrative: SynNarrative
    highlights: List[SynFinding] = Field(default_factory=list)
    risks: List[SynFinding] = Field(default_factory=list)
    recommended_actions: List[SynRecommendedAction] = Field(default_factory=list)
    classification_overrides: List[SynClassificationOverride] = Field(default_factory=list)
    analysis_notes: str = ""
