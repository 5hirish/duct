"""Structured output compatibility for ADK.

ADK has no with_structured_output() equivalent. Instead, the SynthesisAgent
outputs raw JSON text which we parse here with Pydantic validation.
"""

from __future__ import annotations

import logging

from agents.insights.schema import SynthesisSchema

logger = logging.getLogger(__name__)


def parse_synthesis_from_text(raw_text: str) -> SynthesisSchema | None:
    """Parse raw LLM text into SynthesisSchema, handling markdown fences."""
    text = raw_text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n", 1)
        if len(lines) > 1:
            text = lines[1]
        text = text.rsplit("```", 1)[0].strip()

    try:
        return SynthesisSchema.model_validate_json(text)
    except Exception:
        pass

    # Fallback: extract the outermost {...} block
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return SynthesisSchema.model_validate_json(text[start:end])
        except Exception:
            logger.warning(
                "parse_synthesis_from_text: could not validate extracted JSON block (%d chars)",
                end - start,
            )

    logger.error("parse_synthesis_from_text: all parse attempts failed")
    return None
