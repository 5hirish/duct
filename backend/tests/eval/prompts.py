"""Prompts for the evaluation judge — kept in one file for easy review.

These are the only natural-language instructions the judge model sees, besides
the rubric text (which ``render_rubric`` formats from the Rubric definition).
Tune the judge's grading behaviour here rather than in judge.py.
"""

from __future__ import annotations

from tests.eval.rubric import Rubric

# The judge's persona + grading instructions (Gemini `system_instruction`).
JUDGE_SYSTEM_PROMPT = (
    "You are a rigorous content-quality evaluator. You grade a single "
    "AI-generated deliverable against a rubric in order to catch model-output "
    "degradation, so be critical and evidence-based: reserve 5 for genuinely "
    "excellent work and do not inflate scores.\n\n"
    "Score every rubric DIMENSION from 1 to 5 (1=broken, 2=weak, 3=acceptable, "
    "4=strong, 5=excellent) with a one- or two-sentence rationale citing "
    "specific evidence from the text or images. Answer every MARKER as whether "
    "the described condition is present in the artifact. Use the exact keys "
    "given. When images are provided, judge the image dimensions by actually "
    "inspecting the pixels, not the prompts."
)

# Appended to the system instruction so the model emits parseable JSON.
JSON_OUTPUT_INSTRUCTION = (
    "Return ONLY a JSON object (no prose, no code fence) with this shape:\n"
    '{"dimensions":[{"key":str,"score":1-5,"rationale":str}],'
    '"markers":[{"key":str,"satisfied":bool,"evidence":str}],"summary":str}'
)


def render_rubric(rubric: Rubric) -> str:
    """Format a rubric's dimensions + markers into the text shown to the judge."""
    lines = [f"# Rubric: {rubric.name}", "", "## Dimensions — score each 1–5 using the exact key"]
    for d in rubric.dimensions:
        lines.append(f"- key=`{d.key}` — {d.title}: {d.description}")
    if rubric.markers:
        lines.append("")
        lines.append("## Markers — answer satisfied=true/false using the exact key")
        for m in rubric.markers:
            req = "must be ABSENT" if m.kind == "forbidden" else "must be PRESENT"
            lines.append(f"- key=`{m.key}` ({req}): {m.description}")
    return "\n".join(lines)
