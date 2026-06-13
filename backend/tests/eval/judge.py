"""The evaluation judge — a single vision-capable Claude call.

``evaluate()`` renders a rubric + artifact (text and images) into one Messages
API request, asks the judge for structured per-dimension scores and marker
checks, validates the result against ``JudgeVerdict``, and returns a computed
``Scorecard``.

Vision is the point: image dimensions (composition, on-brand styling, prompt
fidelity) can only be graded by actually looking at the generated pixels, so an
artifact's images are attached as image blocks.
"""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field

from tests.eval.client import DEFAULT_JUDGE_MODEL, build_judge_client
from tests.eval.rubric import Rubric
from tests.eval.verdict import JudgeVerdict, Scorecard, build_scorecard

_MAX_IMAGES = 12
_MAX_IMAGE_WIDTH = 768  # downscale heavy 9:16 renders to keep vision tokens sane


@dataclass
class JudgeImage:
    """One image to put in front of the judge, with a label for cross-reference."""

    label: str
    mime_type: str
    data: bytes


@dataclass
class JudgeArtifact:
    """The deliverable under evaluation: a text rendering plus its images."""

    title: str
    body: str
    images: list[JudgeImage] = field(default_factory=list)


def evaluate(
    rubric: Rubric,
    artifact: JudgeArtifact,
    *,
    model: str = DEFAULT_JUDGE_MODEL,
    client=None,
    max_tokens: int = 4096,
) -> Scorecard:
    """Grade ``artifact`` against ``rubric`` with the Claude judge.

    ``client`` defaults to one built from the resolved credentials. Auth errors
    propagate so callers can treat a non-working credential as a skip.
    """
    client = client or build_judge_client()

    content: list[dict] = [
        {"type": "text", "text": _render_rubric(rubric)},
        {"type": "text", "text": f"# Artifact under review: {artifact.title}\n\n{artifact.body}"},
    ]
    if artifact.images:
        content.append({
            "type": "text",
            "text": "# Images (each is labeled — inspect them for the image dimensions and markers):",
        })
        for img in artifact.images[:_MAX_IMAGES]:
            data, mime = _downscale(img.data, img.mime_type)
            content.append({"type": "text", "text": f"Image — {img.label}:"})
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": base64.b64encode(data).decode("ascii"),
                },
            })

    verdict = _run_judge(client, model, max_tokens, content)
    return build_scorecard(rubric, verdict)


# ---------------------------------------------------------------------------
# Judge call — prefer the SDK's structured-output helper, fall back to JSON mode
# ---------------------------------------------------------------------------


def _run_judge(client, model: str, max_tokens: int, content: list[dict]) -> JudgeVerdict:
    system = _system_prompt()
    messages = [{"role": "user", "content": content}]

    # Preferred path: messages.parse validates against the Pydantic schema and
    # strips JSON-schema constraints structured outputs doesn't support.
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_format=JudgeVerdict,
        )
        parsed = getattr(resp, "parsed_output", None) or getattr(resp, "parsed", None)
        if parsed is not None:
            return parsed
        return _verdict_from_text(resp)  # e.g. a refusal — recover from text
    except (AttributeError, TypeError):
        # An SDK without messages.parse / output_format — ask for JSON in the
        # prompt and parse it. Same model, same images, no schema features.
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system + "\n\n" + _json_instruction(),
            messages=messages,
        )
        return _verdict_from_text(resp)


def _verdict_from_text(resp) -> JudgeVerdict:
    text = "".join(
        getattr(b, "text", "") for b in (getattr(resp, "content", None) or [])
        if getattr(b, "type", None) == "text"
    ).strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    return JudgeVerdict.model_validate(json.loads(text))


def _downscale(data: bytes, mime: str) -> tuple[bytes, str]:
    """Best-effort downscale to ``_MAX_IMAGE_WIDTH``. Returns the original bytes
    unchanged if Pillow is unavailable or the bytes aren't a decodable image."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if img.width > _MAX_IMAGE_WIDTH:
            height = max(1, round(img.height * _MAX_IMAGE_WIDTH / img.width))
            img = img.resize((_MAX_IMAGE_WIDTH, height))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, mime


def _system_prompt() -> str:
    return (
        "You are a rigorous content-quality evaluator. You grade a single "
        "AI-generated deliverable against a rubric in order to catch model-"
        "output degradation, so be critical and evidence-based: reserve 5 for "
        "genuinely excellent work and do not inflate scores.\n\n"
        "Score every rubric DIMENSION from 1 to 5 (1=broken, 2=weak, "
        "3=acceptable, 4=strong, 5=excellent) with a one- or two-sentence "
        "rationale citing specific evidence from the text or images. Answer "
        "every MARKER as whether the described condition is present in the "
        "artifact. Use the exact keys given. When images are provided, judge "
        "the image dimensions by actually inspecting the pixels, not the prompts."
    )


def _render_rubric(rubric: Rubric) -> str:
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


def _json_instruction() -> str:
    return (
        "Return ONLY a JSON object (no prose, no code fence) with this shape:\n"
        '{"dimensions":[{"key":str,"score":1-5,"rationale":str}],'
        '"markers":[{"key":str,"satisfied":bool,"evidence":str}],"summary":str}'
    )
