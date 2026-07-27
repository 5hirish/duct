"""Modular LLM-as-judge evaluation harness for Duct agents.

A small, agent-agnostic framework for grading real agent output with a Claude
judge instead of brittle string assertions. The motivation is degradation
defence: model output drifts in ways exact-match assertions can't catch (a
weaker hook, an off-brand image, a flattened narrative all still "validate"),
so we score the deliverable on rubric dimensions and gate on thresholds.

Pieces:
  - ``Rubric`` / ``Dimension`` / ``Marker`` (rubric.py) — what "good" means.
  - ``JudgeVerdict`` / ``Scorecard`` (verdict.py)        — the judge's output
                                                           and our computed
                                                           pass/fail.
  - ``evaluate()`` (judge.py)                            — runs the judge
                                                           (vision-capable).
  - ``assert_scorecard()`` (assertions.py)               — the pytest gate.
  - ``judge_available()`` / ``build_judge_client()`` (client.py) — credentials.

Reusable across agent types — the content e2e supplies a content rubric; audit
and insights can supply their own. The judge is the only network dependency and
degrades to a clean skip when no Claude credential is available.
"""

from tests.eval.assertions import ScorecardError, assert_scorecard
from tests.eval.client import (
    DEFAULT_JUDGE_MODEL,
    JudgeUnavailable,
    build_judge_client,
    judge_available,
    resolve_judge_api_key,
)
from tests.eval.judge import JudgeArtifact, JudgeImage, evaluate
from tests.eval.rubric import Dimension, Marker, Rubric
from tests.eval.verdict import (
    DimensionScore,
    JudgeVerdict,
    MarkerVerdict,
    Scorecard,
    build_scorecard,
)

__all__ = [
    "DEFAULT_JUDGE_MODEL",
    "Dimension",
    "DimensionScore",
    "JudgeArtifact",
    "JudgeImage",
    "JudgeUnavailable",
    "JudgeVerdict",
    "Marker",
    "MarkerVerdict",
    "Rubric",
    "Scorecard",
    "ScorecardError",
    "assert_scorecard",
    "build_judge_client",
    "build_scorecard",
    "evaluate",
    "judge_available",
    "resolve_judge_api_key",
]
