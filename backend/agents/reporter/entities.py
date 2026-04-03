"""Closed vocabularies for synthesis structured output (JSON schema / LLM)."""

from __future__ import annotations

from enum import StrEnum


class SynDataSource(StrEnum):
    """Upstream data source named in evidence."""

    GOOGLE_ADS = "google_ads"


class SynEntityType(StrEnum):
    """Entity granularity for evidence attribution."""

    CAMPAIGN = "campaign"


class SynFindingType(StrEnum):
    """Finding classification for highlights and risks."""

    WIN = "win"
    RISK = "risk"
    WATCH = "watch"


class SynConfidenceLevel(StrEnum):
    """Confidence attached to a finding."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SynActionType(StrEnum):
    """Recommended action category."""

    SCALE = "scale"
    MONITOR = "monitor"
    PAUSE = "pause"
    REFRESH = "refresh"
    TIGHTEN = "tighten"
    INVESTIGATE = "investigate"


class SynActionPriority(StrEnum):
    """Priority tier for a recommended action."""

    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
