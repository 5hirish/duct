"""The evaluation judge — a single vision-capable Gemini call.

``evaluate()`` renders a rubric + artifact (text and images) into one Gemini
``generate_content`` request, asks for structured per-dimension scores and
marker checks as JSON, validates the result against ``JudgeVerdict``, and
returns a computed ``Scorecard``.

We call google-genai directly (the Gemini stack the v2/ADK engine sits on)
rather than ADK: the judge is one multimodal call that must see the images and
return a typed verdict, which google-genai does natively. We use the
structured-output API — ``response_schema=JudgeVerdict`` — so the model is
constrained to the Pydantic shape and ``response.parsed`` comes back validated
(see service/google/brief.py for the same response_schema pattern); a text-JSON
fallback (``_parse_verdict``) covers the rare case ``parsed`` is empty.

Vision is the point — and Gemini's native multimodality is the reason this lives
on Gemini: image dimensions (composition, legibility at a glance, on-brand
styling, prompt fidelity) can only be graded by actually looking at the pixels,
so an artifact's images are attached as image parts in the same request.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

from tests.eval.client import DEFAULT_JUDGE_MODEL, build_judge_client
from tests.eval.prompts import build_judge_system_prompt, render_rubric
from tests.eval.rubric import Rubric
from tests.eval.verdict import JudgeVerdict, Scorecard, build_scorecard

_MAX_IMAGES = 12
_MAX_IMAGE_WIDTH = 768  # downscale heavy 9:16 renders to keep the request light


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
    model: str | None = None,
    client=None,
    max_output_tokens: int = 4096,
) -> Scorecard:
    """Grade ``artifact`` against ``rubric`` with the Gemini judge.

    ``client`` defaults to one built from the resolved Gemini key. API errors
    (rate limit, 5xx) propagate so callers can treat them as a skip.
    """
    client = client or build_judge_client()
    model = model or os.environ.get("DUCT_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL
    verdict = _run_judge(client, model, rubric, artifact, max_output_tokens)
    return build_scorecard(rubric, verdict)


def _run_judge(client, model: str, rubric: Rubric, artifact: JudgeArtifact, max_output_tokens: int) -> JudgeVerdict:
    from google.genai import types

    parts = [
        types.Part.from_text(text=render_rubric(rubric)),
        types.Part.from_text(text=f"# Artifact under review: {artifact.title}\n\n{artifact.body}"),
    ]
    if artifact.images:
        parts.append(types.Part.from_text(
            text="# Images (each is labeled — inspect them for the image dimensions and markers):"
        ))
        for img in artifact.images[:_MAX_IMAGES]:
            data, mime = _downscale(img.data, img.mime_type)
            parts.append(types.Part.from_text(text=f"Image — {img.label}:"))
            parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    config = types.GenerateContentConfig(
        system_instruction=build_judge_system_prompt(rubric.persona),
        response_mime_type="application/json",
        response_schema=JudgeVerdict,
        temperature=0.2,
        max_output_tokens=max_output_tokens,
    )
    resp = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=parts)],
        config=config,
    )
    # Structured output gives us the validated object directly; fall back to
    # parsing the text only if the SDK didn't populate `.parsed`.
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, JudgeVerdict):
        return parsed
    return _parse_verdict(resp)


def _parse_verdict(resp) -> JudgeVerdict:
    """Pull the JSON verdict out of a Gemini response and validate it."""
    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        # Some SDK versions only expose text via candidates[].content.parts[].text
        chunks: list[str] = []
        for cand in (getattr(resp, "candidates", None) or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                piece = getattr(part, "text", None)
                if piece:
                    chunks.append(piece)
        text = "".join(chunks).strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    return JudgeVerdict.model_validate_json(text)


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
