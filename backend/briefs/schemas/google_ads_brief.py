"""Typed schema for the Google Ads MVP brief.

The normalized payload is the contract between fetch/normalize logic, any future
LLM synthesis step, and the HTML renderer. Keep this file stable and extend by
adding optional fields instead of reshaping existing sections.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional


FindingType = Literal["win", "risk", "watch"]
ActionType = Literal["scale", "monitor", "pause", "refresh", "tighten", "investigate"]
ConfidenceLevel = Literal["low", "medium", "high"]


@dataclass
class MetricValue:
    value: float
    formatted: str


@dataclass
class DeltaValue:
    absolute: float
    percent: float
    direction: Literal["up", "down", "flat"]
    formatted: str


@dataclass
class ComparisonMetric:
    current: MetricValue
    previous: MetricValue
    delta: DeltaValue


@dataclass
class EvidenceSource:
    source: str
    entity_type: str
    entity_name: str
    metric: str
    note: str


@dataclass
class SourceMetadata:
    source: str
    export_type: str
    generated_at: str
    window_current: str
    window_previous: str
    currency_code: str
    account_name: str
    account_id: Optional[str] = None
    source_file: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    theme: Optional[str] = None


@dataclass
class CampaignPerformance:
    campaign_name: str
    campaign_id: Optional[str]
    channel_type: Optional[str]
    status: Optional[str]
    clicks: int
    impressions: int
    spend: float
    ctr: float
    average_cpc: float
    conversions: float
    cost_per_conversion: float
    conversion_value: float
    roas: float
    action: ActionType
    action_reason: str
    evidence: List[str] = field(default_factory=list)
    evidence_sources: List[EvidenceSource] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    finding_id: str
    type: FindingType
    title: str
    evidence: List[str]
    impact: str
    recommended_action: str
    confidence: ConfidenceLevel
    related_campaigns: List[str] = field(default_factory=list)
    evidence_sources: List[EvidenceSource] = field(default_factory=list)


@dataclass
class RecommendedAction:
    action_id: str
    type: ActionType
    title: str
    detail: str
    priority: Literal["p1", "p2", "p3"]
    owner: str
    related_campaigns: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    evidence_sources: List[EvidenceSource] = field(default_factory=list)


@dataclass
class AccountSummary:
    spend: MetricValue
    clicks: MetricValue
    impressions: MetricValue
    ctr: MetricValue
    average_cpc: MetricValue
    conversions: MetricValue
    cost_per_conversion: MetricValue
    conversion_value: MetricValue
    roas: MetricValue


@dataclass
class PeriodComparison:
    spend: ComparisonMetric
    conversions: ComparisonMetric
    cost_per_conversion: ComparisonMetric
    conversion_value: ComparisonMetric
    roas: ComparisonMetric
    clicks: ComparisonMetric
    impressions: ComparisonMetric
    ctr: ComparisonMetric


@dataclass
class BriefNarrative:
    verdict: str
    summary: str
    operator_takeaway: str


@dataclass
class GoogleAdsBrief:
    source_metadata: SourceMetadata
    account_summary: AccountSummary
    period_comparison: PeriodComparison
    campaigns: List[CampaignPerformance]
    highlights: List[Finding]
    risks: List[Finding]
    recommended_actions: List[RecommendedAction]
    narrative: BriefNarrative

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

