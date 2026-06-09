"""Shared output components — reusable building blocks that agents compose.

The cross-cutting finding/action/evidence/narrative shapes are defined once here
so outputs stay consistent across agents. Insights composes these today (its
SynFinding / SynRecommendedAction / SynNarrative extend the bases); audit's
finding shape already aligns on the same field names.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceSource(BaseModel):
    """A pointer to where a claim came from — a connector entity, a crawled URL,
    or a web source. Generalizes insights' SynEvidenceSource and audit's
    AffectedUrl."""

    source: str = ""              # "google_ads" | "ga4" | "gsc" | "crawl" | "web" | …
    entity_type: str = ""         # "campaign" | "page" | "query" | …
    entity_name: str = ""
    metric: str = ""
    value: str = ""               # e.g. "13 chars", "HTTP 404", "ROAS 0.64x"
    url: str = ""
    note: str = ""


class Narrative(BaseModel):
    """The headline read of an artifact."""

    verdict: str = ""
    summary: str = ""
    takeaway: str = ""            # operator_takeaway / strategic_narrative


class Finding(BaseModel):
    """Minimal common base for an observation. Each agent extends this with its
    own domain fields — insights adds type/confidence/recommended_action/
    related_campaigns; audit adds severity/affected_urls/effort — so the shared
    ``id``/``title``/``impact``/``evidence`` surface stays consistent across agents."""

    id: str = ""
    title: str = ""
    impact: str = ""
    evidence: list[str] = Field(default_factory=list)
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    """Minimal common base for a prioritized next step; agents extend with their
    own fields (insights: type/priority/owner/related_campaigns)."""

    id: str = ""
    title: str = ""
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)
