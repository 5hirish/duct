"""Shared output vocabulary — the standard envelope + reusable components every
agent's result composes.

Each agent keeps its genuinely-unique fields, but the cross-cutting shapes
(metadata envelope, findings, recommended actions, evidence, narrative) are
defined once here so the frontend reads one consistent structure across audit,
content, and insights. Adoption (refactoring SynthesisSchema / AuditReport /
PlanDraft to extend these) happens per agent; this module is the target.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ArtifactMetadata(BaseModel):
    """Envelope metadata present on every agent artifact.

    ``source_metadata`` carries the existing app contract keys (``theme``,
    ``generated_at``) so the frontend's accent-color / timestamp resolution is
    unchanged.
    """

    agent_type: str = ""
    generated_at: str = ""
    version: str = ""
    source_metadata: dict = Field(default_factory=dict)


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
    """The headline read of the artifact."""

    verdict: str = ""
    summary: str = ""
    takeaway: str = ""            # operator_takeaway / strategic_narrative


class Finding(BaseModel):
    """A single observation. Severity/confidence are free strings so each agent
    keeps its own scale (insights confidence; audit fail/warn/opportunity)."""

    id: str = ""
    title: str = ""
    description: str = ""
    severity: str = ""
    confidence: str = ""
    impact: str = ""
    recommendation: str = ""
    evidence: list[str] = Field(default_factory=list)
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    """A prioritized next step."""

    id: str = ""
    title: str = ""
    detail: str = ""
    priority: str = ""            # "high" | "medium" | "low"
    owner: str = ""
    effort: str = ""
    evidence: list[str] = Field(default_factory=list)


class BaseArtifact(BaseModel):
    """Common envelope every agent's top-level output extends.

    Agents add their unique fields (insights ``dashboard_spec``, audit
    ``structured_data`` / ``html_report``, content ``slides`` / ``days``) on
    their own subclasses; these fields stay standard.
    """

    metadata: ArtifactMetadata = Field(default_factory=ArtifactMetadata)
    headline: str = ""
    executive_summary: str = ""
    narrative: Narrative | None = None
    findings: list[Finding] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
