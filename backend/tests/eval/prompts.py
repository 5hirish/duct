"""Prompts for the evaluation judge — kept in one file for easy review.

These are the only natural-language instructions the judge model sees, besides
the rubric text (which ``render_rubric`` formats from the Rubric definition).
Tune the judge's grading behaviour — and the end-user persona it evaluates
from — here.

We deliberately do NOT instruct a JSON shape: the judge is called with Gemini's
structured-output API (``response_schema=JudgeVerdict``), so the model is
constrained to the schema and there's nothing to describe in prose.
"""

from __future__ import annotations

from tests.eval.rubric import Rubric

# Base evaluator framing. The verbosity/formatting line counters the well-known
# LLM-judge verbosity bias (judges over-reward long, fluent answers).
_EVALUATOR_PREAMBLE = (
    "You are a rigorous third-party quality evaluator for AI-generated content. "
    "Your job is to catch model-output degradation, so be critical and "
    "evidence-based: reserve 5 for genuinely excellent work, never inflate "
    "scores, and do not reward length, formatting, or fluent prose on their own."
)

# Inserted when the rubric defines a persona — the "masking as the user" lens.
_PERSONA_TEMPLATE = (
    "\n\n## Evaluate as this end user\n{persona}\n\n"
    "First react the way this person actually would in the moment — what grabs "
    "them, what they skim past, where they lose interest, and what would make "
    "them stop, save, or share. Then translate that gut reaction into the scores."
)

_SCORING_INSTRUCTIONS = (
    "\n\n## Scoring\n"
    "Score every rubric DIMENSION from 1 to 5 (1=broken, 2=weak, 3=acceptable, "
    "4=strong, 5=excellent) with a one- or two-sentence rationale citing specific "
    "evidence from the text or images. For every MARKER, report whether the "
    "described condition is PRESENT in the artifact (just report what you observe; "
    "the pass/fail logic is applied separately). Use the exact keys given. When "
    "images are provided, judge them by actually looking at the pixels — "
    "composition, legibility at a glance, on-brand styling — not by the prompts."
)


def build_judge_system_prompt(persona: str = "") -> str:
    """Compose the judge's system instruction, embedding the end-user persona."""
    parts = [_EVALUATOR_PREAMBLE]
    if persona.strip():
        parts.append(_PERSONA_TEMPLATE.format(persona=persona.strip()))
    parts.append(_SCORING_INSTRUCTIONS)
    return "".join(parts)


def render_rubric(rubric: Rubric) -> str:
    """Format a rubric's dimensions + markers into the text shown to the judge."""
    lines = [f"# Rubric: {rubric.name}", "", "## Dimensions — score each 1–5 using the exact key"]
    for d in rubric.dimensions:
        lines.append(f"- key=`{d.key}` — {d.title}: {d.description}")
    if rubric.markers:
        lines.append("")
        lines.append("## Markers — set satisfied=true if the described condition is present, false if absent")
        for m in rubric.markers:
            lines.append(f"- key=`{m.key}`: {m.description}")
    return "\n".join(lines)
