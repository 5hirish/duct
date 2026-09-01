"""Parse a synthesis out of raw model text, when structured output is not available.

Not every path can ask the provider for a typed object. Gemini's
``response_schema`` (controlled generation) rejects ``SynthesisSchema`` outright
because of its ``additionalProperties`` nodes, and the Claude Agent SDK returns
a text result rather than a parsed one. Those paths ask the model for JSON and
hand the answer here.

Models are inconsistent about how they wrap it — a bare object, a ```json fence,
or an object with prose either side — so parsing is deliberately tolerant of all
three. That tolerance is not cosmetic: fenced output used to parse as empty and
lose a whole brief.

Lived under ``v2/`` while the ADK engine was the only caller that needed it. It
was never ADK-specific — nothing here imports a framework — so it moved up to
``agents/insights/`` when that engine was removed and v3 was left as the caller.
"""

from __future__ import annotations

import logging

from agents.insights.schema import SynthesisSchema

logger = logging.getLogger(__name__)


def _strip_to_json(raw_text: str) -> str:
    """Strip markdown fences and trailing prose, returning the JSON substring.

    Handles ```json ... ``` / ``` ... ``` fences and, failing that, extracts the
    outermost ``{...}`` block. Returns the original (stripped) text if no object
    delimiters are found.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n", 1)
        if len(lines) > 1:
            text = lines[1]
        text = text.rsplit("```", 1)[0].strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return text[start:end]
    return text


def validate_synthesis(raw_text: str) -> tuple[SynthesisSchema | None, str]:
    """Parse + validate raw LLM text into SynthesisSchema.

    Returns ``(schema, "")`` on success or ``(None, error_message)`` on failure.
    The error message is the Pydantic validation error (or a parse error). It is
    kept separate from the return value rather than raised so a caller can tell
    "the model wrote nothing" apart from "the model wrote the wrong shape" — the
    ADK engine used it to drive a repair pass, and ``parse_synthesis_from_text``
    now logs it, which is what makes a failed brief diagnosable after the fact.
    """
    if not raw_text or not raw_text.strip():
        return None, "empty synthesis output"
    candidate = _strip_to_json(raw_text)
    try:
        return SynthesisSchema.model_validate_json(candidate), ""
    except Exception as exc:  # ValidationError or JSON error
        return None, str(exc)


def parse_synthesis_from_text(raw_text: str) -> SynthesisSchema | None:
    """Parse raw LLM text into SynthesisSchema, handling markdown fences.

    Thin wrapper over validate_synthesis kept for call-site compatibility.
    """
    parsed, error = validate_synthesis(raw_text)
    if parsed is None:
        logger.error("parse_synthesis_from_text: %s", error[:200] if error else "failed")
    return parsed
