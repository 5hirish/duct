"""Structured output compatibility for ADK.

ADK has no with_structured_output() equivalent, and Gemini's response_schema
(controlled generation) rejects the SynthesisSchema JSON Schema because of its
``additionalProperties`` nodes — so we cannot use ``LlmAgent(output_schema=...)``
on Gemini. Instead the SynthesisAgent emits raw JSON text which we parse and
validate here. ``validate_synthesis`` additionally surfaces the validation error
so the v2 dynamic workflow can feed it back to a repair pass (see agents.py).
"""

from __future__ import annotations

import json
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
    The error message is the Pydantic validation error (or a parse error) and is
    fed back to the synthesis repair pass so the model can fix the exact fields.
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


def extract_json_dict(raw_text: str) -> dict:
    """Best-effort parse of an LLM JSON-object string into a dict.

    Tolerant of markdown fences and surrounding prose (the data-fetch agent is
    asked for fence-less JSON but models don't always comply). Returns ``{}`` if
    nothing parseable is found.
    """
    if isinstance(raw_text, dict):
        return raw_text
    if not raw_text:
        return {}
    candidate = _strip_to_json(raw_text)
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("extract_json_dict: could not parse JSON object from text")
        return {}
