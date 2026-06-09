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
