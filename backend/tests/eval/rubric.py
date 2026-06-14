"""Rubric primitives for the agent evaluation harness.

A rubric is the machine-checkable definition of "good output" for one agent
deliverable: a set of weighted scoring dimensions plus pass/fail markers. It is
deliberately agent-agnostic — the content agent supplies a content rubric, and
audit / insights can supply their own — so the judge (``judge.py``) and the
pass gate (``assertions.py``) never need to know what they are grading.

The point of a rubric (vs. exact-match asserts) is degradation defence: model
output drifts in ways string assertions can't catch — a weaker hook, an
off-brand image, a flattened narrative all still "validate" structurally — so
we score the deliverable on rubric dimensions and gate on thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MarkerKind = Literal["required", "forbidden"]


@dataclass(frozen=True)
class Dimension:
    """One scored axis of quality, graded 1–5 by the judge.

    ``min_score`` is the floor below which the artifact fails on this axis alone
    (independent of the weighted overall) — use it for non-negotiables like a
    legible hook. ``weight`` scales the dimension's contribution to the overall.
    """

    key: str
    title: str
    description: str
    weight: float = 1.0
    min_score: int = 1


@dataclass(frozen=True)
class Marker:
    """A binary check the judge answers: is the described condition present?

    ``kind`` decides how the answer gates:
      - ``"required"``  → must be present (judge ``satisfied=True``), else fail.
      - ``"forbidden"`` → must be absent (judge ``satisfied=False``), else fail.

    Phrase ``description`` as the thing to look for, not the verdict, so the
    judge always answers the same question ("is this true of the artifact?").
    """

    key: str
    description: str
    kind: MarkerKind = "required"


@dataclass(frozen=True)
class Rubric:
    """A complete grading definition for one artifact type.

    ``pass_threshold`` is the minimum weighted overall (on the 1–5 scale). The
    artifact passes only when the overall is at or above it AND every dimension
    clears its ``min_score`` AND every marker gates clean.

    ``persona`` is the end user the judge should embody while grading — a
    third-party critic "masking as the user" (e.g. a sound-off TikTok scroller
    for short-form content). It shapes the judge's gut reaction; the dimensions
    still define what gets scored. Leave empty for a neutral expert evaluator.
    """

    name: str
    dimensions: list[Dimension]
    markers: list[Marker] = field(default_factory=list)
    pass_threshold: float = 3.5
    persona: str = ""

    def dimension_keys(self) -> list[str]:
        return [d.key for d in self.dimensions]

    def marker_keys(self) -> list[str]:
        return [m.key for m in self.markers]
