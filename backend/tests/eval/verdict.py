"""The judge's structured verdict and the scorecard we compute from it.

``JudgeVerdict`` is what the Claude judge returns (validated structured output).
``Scorecard`` is what WE compute from a verdict + the rubric — the weighted
overall, the pass/fail decision, and the human-readable failure list. Keeping
scoring deterministic on our side (rather than asking the model for a final
pass/fail) makes thresholds auditable and stable across judge runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tests.eval.rubric import Rubric

# Literal (not ge/le) so the JSON schema emits an `enum` — natively supported by
# structured outputs, with no constraint-stripping needed.
Score = Literal[1, 2, 3, 4, 5]


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Must match one of the rubric dimension keys exactly.")
    score: Score = Field(description="1=broken, 2=weak, 3=acceptable, 4=strong, 5=excellent.")
    rationale: str = Field(description="One or two sentences citing specific evidence.")


class MarkerVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Must match one of the rubric marker keys exactly.")
    satisfied: bool = Field(description="True if the described condition is present in the artifact.")
    evidence: str = Field(description="The specific text or visual detail that decided this.")


class JudgeVerdict(BaseModel):
    """Structured-output schema handed to the judge model."""

    model_config = ConfigDict(extra="forbid")

    dimensions: list[DimensionScore]
    markers: list[MarkerVerdict]
    summary: str = Field(description="A 2–3 sentence overall assessment.")


@dataclass
class Scorecard:
    """The computed result of grading one artifact against one rubric."""

    rubric_name: str
    overall: float
    passed: bool
    dimension_scores: dict[str, int]
    failures: list[str]
    verdict: JudgeVerdict

    def as_dict(self) -> dict:
        return {
            "rubric": self.rubric_name,
            "overall": round(self.overall, 2),
            "passed": self.passed,
            "dimension_scores": self.dimension_scores,
            "failures": self.failures,
            "summary": self.verdict.summary,
            "dimensions": [d.model_dump() for d in self.verdict.dimensions],
            "markers": [m.model_dump() for m in self.verdict.markers],
        }

    def as_markdown(self) -> str:
        lines: list[str] = []
        status = "✅ PASS" if self.passed else "❌ FAIL"
        lines.append(f"### Eval scorecard — {self.rubric_name}: {status}  (overall {self.overall:.2f})")
        lines.append("")
        lines.append("| Dimension | Score | Rationale |")
        lines.append("| --- | :---: | --- |")
        for d in self.verdict.dimensions:
            rationale = d.rationale.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {d.key} | {d.score}/5 | {rationale} |")
        if self.verdict.markers:
            lines.append("")
            lines.append("| Marker | Satisfied | Evidence |")
            lines.append("| --- | :---: | --- |")
            for m in self.verdict.markers:
                evidence = m.evidence.replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {m.key} | {'yes' if m.satisfied else 'no'} | {evidence} |")
        lines.append("")
        lines.append(f"**Summary:** {self.verdict.summary}")
        if self.failures:
            lines.append("")
            lines.append("**Failures:**")
            for f in self.failures:
                lines.append(f"- {f}")
        return "\n".join(lines)


def build_scorecard(rubric: Rubric, verdict: JudgeVerdict) -> Scorecard:
    """Fold a judge verdict into a pass/fail scorecard against the rubric.

    Pure and deterministic — unit-testable offline with a fabricated verdict.
    """
    score_by_key = {d.key: int(d.score) for d in verdict.dimensions}
    marker_by_key = {m.key: m for m in verdict.markers}
    failures: list[str] = []

    total_weight = 0.0
    weighted_sum = 0.0
    dimension_scores: dict[str, int] = {}
    for dim in rubric.dimensions:
        score = score_by_key.get(dim.key)
        if score is None:
            failures.append(f"dimension '{dim.key}' missing from judge verdict")
            score = 0
        dimension_scores[dim.key] = score
        total_weight += dim.weight
        weighted_sum += dim.weight * score
        if score < dim.min_score:
            failures.append(
                f"{dim.key}: scored {score} < required minimum {dim.min_score} ({dim.title})"
            )
    overall = (weighted_sum / total_weight) if total_weight else 0.0

    for marker in rubric.markers:
        mv = marker_by_key.get(marker.key)
        if mv is None:
            failures.append(f"marker '{marker.key}' missing from judge verdict")
            continue
        if marker.kind == "required" and not mv.satisfied:
            failures.append(f"required marker '{marker.key}' not satisfied — {mv.evidence}")
        elif marker.kind == "forbidden" and mv.satisfied:
            failures.append(f"forbidden marker '{marker.key}' present — {mv.evidence}")

    if overall < rubric.pass_threshold:
        failures.append(f"overall {overall:.2f} < pass threshold {rubric.pass_threshold}")

    return Scorecard(
        rubric_name=rubric.name,
        overall=overall,
        passed=not failures,
        dimension_scores=dimension_scores,
        failures=failures,
        verdict=verdict,
    )
