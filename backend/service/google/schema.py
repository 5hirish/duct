"""Typed Google Ads brief payload (JSON contract for normalize → synthesis → app).

The normalized payload is the contract between fetch/normalize logic, any LLM
synthesis step, and the report renderer. Keep this module stable; extend with
optional fields instead of reshaping existing sections.

Closed vocabularies are ``StrEnum``s so the brief builder, metrics, and synthesis
schemas share one reporting vocabulary while JSON values stay unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from utils.helpers import json_safe


class EvidenceDataSource(StrEnum):
    """Upstream connector named on evidence (wire: ``source``)."""

    GOOGLE_ADS = "google_ads"


class EvidenceEntityType(StrEnum):
    """Entity granularity for evidence attribution."""

    CAMPAIGN = "campaign"
    AD_GROUP = "ad_group"
    SEARCH_TERM = "search_term"
    DEVICE = "device"
    GEO = "geo"


class FindingType(StrEnum):
    """Finding classification for highlights and risks."""

    WIN = "win"
    RISK = "risk"
    WATCH = "watch"


class ConfidenceLevel(StrEnum):
    """Confidence attached to a finding."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionType(StrEnum):
    """Recommended action / campaign disposition category."""

    SCALE = "scale"
    MONITOR = "monitor"
    PAUSE = "pause"
    REFRESH = "refresh"
    REFINE = "refine"
    INVESTIGATE = "investigate"


class ActionPriority(StrEnum):
    """Priority tier for a recommended action (sort order: urgent → high → medium → low)."""

    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DeltaDirection(StrEnum):
    """Signed change bucket for period-over-period metrics."""

    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class MetricFormatKind(StrEnum):
    """How raw metric floats are formatted into ``MetricValue.formatted`` / delta text.

    ``CURRENCY`` uses the account currency code (see ``utils.formatting.money``).
    ``MULTIPLIER`` is for unitless ratios (e.g. ROAS as revenue/spend), not a metric name.
    """

    CURRENCY = "currency"
    PERCENT = "percent"
    NUMBER = "number"
    MULTIPLIER = "multiplier"


@dataclass
class MetricValue:
    value: float
    formatted: str


@dataclass
class DeltaValue:
    absolute: float
    percent: float
    direction: DeltaDirection
    formatted: str


@dataclass
class ComparisonMetric:
    current: MetricValue
    previous: MetricValue
    delta: DeltaValue


@dataclass
class EvidenceSource:
    source: EvidenceDataSource
    entity_type: EvidenceEntityType
    entity_name: str
    metric: str
    note: str
    connector_entity_id: str = ""


@dataclass
class SourceMetadata:
    source: str
    export_type: str
    generated_at: str
    window_current: str
    window_previous: str
    currency_code: str
    account_name: str
    account_id: str | None = None
    source_file: str | None = None
    notes: list[str] = field(default_factory=list)
    theme: str | None = None


@dataclass
class CampaignPerformance:
    campaign_name: str
    campaign_id: str | None
    channel_type: str | None
    status: str | None
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
    evidence: list[str] = field(default_factory=list)
    evidence_sources: list[EvidenceSource] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    finding_id: str
    type: FindingType
    title: str
    evidence: list[str]
    impact: str
    recommended_action: str
    confidence: ConfidenceLevel
    related_campaigns: list[str] = field(default_factory=list)
    evidence_sources: list[EvidenceSource] = field(default_factory=list)


@dataclass
class RecommendedAction:
    action_id: str
    type: ActionType
    title: str
    detail: str
    priority: ActionPriority
    owner: str
    related_campaigns: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    evidence_sources: list[EvidenceSource] = field(default_factory=list)


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
    campaigns: list[CampaignPerformance]
    highlights: list[Finding]
    risks: list[Finding]
    recommended_actions: list[RecommendedAction]
    narrative: BriefNarrative

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))
