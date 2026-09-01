"""Parsing a synthesis out of raw model text (agents/insights/schema_compat.py).

Lived in `tests/test_insights_v2.py` until the ADK engine was removed. The
helper outlived that engine — v3 still needs it, because the Claude Agent SDK
returns a text result rather than a parsed object — so its coverage moved here
rather than being deleted with the engine.

The behaviour worth pinning is tolerance of how models wrap JSON. Fenced output
parsing as empty is not a hypothetical: it silently lost whole briefs.
"""

from __future__ import annotations

from agents.insights.schema_compat import parse_synthesis_from_text, validate_synthesis


def test_validate_synthesis_separates_empty_from_malformed():
    """(None, msg) on bad input, (schema, "") on good — and the msg says which.

    The error string is the difference between "the model wrote nothing" and
    "the model wrote the wrong shape". A caller that only saw None could not
    tell those apart, and neither could anyone reading the logs afterwards.
    """
    parsed, err = validate_synthesis("")
    assert parsed is None and err

    parsed, err = validate_synthesis('{"verdict": "x"}')  # missing required fields
    assert parsed is None
    assert "validation error" in err.lower()


def test_fences_are_stripped_before_validation():
    """A fenced object must reach the validator as JSON, not as text.

    Asserted through the error *kind*: a fenced payload yields a schema
    validation error (missing fields), not a JSON parse error — which proves the
    candidate was decoded rather than rejected at the fence.
    """
    _, err = validate_synthesis('```json\n{"verdict": "x"}\n```')
    assert "validation error" in err.lower()


def test_unparseable_text_returns_none_rather_than_raising():
    """v3 calls this on whatever the model emitted; it must never raise."""
    assert parse_synthesis_from_text("not json at all") is None
    assert parse_synthesis_from_text("") is None
