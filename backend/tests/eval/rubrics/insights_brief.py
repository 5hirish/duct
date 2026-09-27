"""Rubric for the insights brief, the deliverable Duct is bought for.

The other two rubrics grade on a weighted 1–5 overall. This one gates on
binary markers only and logs the dimensions, for two reasons from the
2026-09-27 eval design: a blended 0.80 hid a failure a HONORED/IGNORED rubric
exposed (Google; Husain & Shankar), and the gate's judge is often the same
model family as the agent under test, whose self-preference moves a score far
more readily than a yes/no about a sentence that is or is not on the page.

A case adds its own markers (the planted finding it must name); the generic
ones below hold for every brief.
"""

from __future__ import annotations

from tests.eval.judge import JudgeArtifact
from tests.eval.rubric import Dimension, Marker, Rubric

GENERIC_MARKERS: tuple[Marker, ...] = (
    Marker(
        "decision_first",
        "The opening two or three sentences state what is happening and what to do about "
        "it, before any table or background.",
    ),
    Marker(
        "comparison",
        "Headline numbers are compared with a previous period (a delta, a share or a "
        "rate beside the number), not stated alone.",
    ),
    Marker(
        "windows_named",
        "Figures say which dates or period they cover, at least once per table or "
        "per finding.",
    ),
    Marker(
        "actionable",
        "At least one action says what to change, the effect expected, and how to check "
        "it worked.",
    ),
    Marker(
        "gaps_named",
        "There is a section or passage saying what could not be checked and which data "
        "source would close each gap.",
    ),
    Marker(
        "invented_source",
        "The brief cites a data source, tool or report that the analysis evidently did not "
        "have (for example Stripe revenue, heatmaps, or survey results in a brief built "
        "only on analytics and search data).",
        kind="forbidden",
    ),
)

DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("analysis", "Analysis depth",
              "Explains a mechanism, not a movement; ties it to the business target."),
    Dimension("prioritisation", "Prioritisation",
              "Ranks by money or the KPI at stake, not by row order or volume."),
    Dimension("clarity", "Clarity", "A reader who stops after the first screen has the answer."),
)


def insights_brief_rubric(extra: tuple[Marker, ...] = ()) -> Rubric:
    return Rubric(
        name="insights_brief",
        dimensions=list(DIMENSIONS),
        markers=[*GENERIC_MARKERS, *extra],
        # Dimensions are logged, never gating: 1 is the floor every score clears.
        pass_threshold=1.0,
        persona=(
            "You are the head of growth who asked the question. You will forward this "
            "brief to your CEO if it is right and delete it if it is vague. You check "
            "every number you are going to repeat."
        ),
    )


def render_brief_artifact(brief: str, *, question: str) -> JudgeArtifact:
    return JudgeArtifact(title=f"Insights brief — {question}", body=brief)
