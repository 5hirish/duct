"""Typed → JSON-Schema bridge for Claude Agent SDK @tool input schemas.

Shared by every v3 agent (content, audit, insights). Lets a tool's input be
defined as a typed Pydantic model — enums via StrEnum, ranges via Field — and
converted to the flat JSON Schema dict the SDK hands to the model, instead of
hand-writing raw JSON.

Why a cleaner is needed: Pydantic's ``model_json_schema()`` is correct but
verbose — it factors enums/nested models into ``$defs`` + ``$ref``, renders
Optionals as ``anyOf: [T, null]``, and stamps ``title``/``default`` everywhere.
The Agent SDK passes the dict to the model VERBATIM (its ``_build_schema`` only
checks that ``type``/``properties`` exist; it does not resolve ``$ref``), so the
indirection and noise reach the model as-is. ``tool_schema`` inlines and tidies.

Version safety: this depends on two external contracts —
  1. Pydantic's ``model_json_schema()`` output shape, and
  2. the SDK passing a ``type``+``properties`` dict through verbatim.
Both are pinned by tests (see tests/test_agent_core.py::test_tool_schema_* for
the Pydantic-shape guard, and the per-agent list_tools tests for the SDK
contract). If a Pydantic or SDK upgrade changes either, those tests fail loudly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Pydantic bookkeeping keys that are noise in a tool schema — stripped at every
# level. If a future Pydantic version introduces a new wrapper key, the
# no-artifacts assertion in the unit test catches it.
_SCHEMA_DROP_KEYS = ("title", "default", "additionalProperties", "$defs")


def tool_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Build a clean, flat JSON Schema dict from a Pydantic model for an SDK
    @tool ``input_schema``.

    Dereferences ``$ref`` in place (inlining enums/nested defs), collapses an
    Optional's ``anyOf: [T, null]`` down to ``T``, and drops
    ``title``/``default``/``additionalProperties``/``$defs`` noise. ``required``
    (fields without a default) and ``enum``/``minimum``/``maximum``/``description``
    are preserved.

    Note: every ``$ref`` is inlined, so a sub-model referenced many times is
    duplicated. Ideal for flat-ish inputs (scalars + enums); for deeply nested
    models with shared sub-defs, the raw ``model_json_schema()`` (with ``$defs``)
    stays more compact — the SDK passes that through fine too.
    """
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})

    def clean(node: Any) -> Any:
        if isinstance(node, list):
            return [clean(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "anyOf" in node:  # collapse an Optional's anyOf:[T, null] -> T
            variants = [a for a in node["anyOf"]
                        if not (isinstance(a, dict) and a.get("type") == "null")]
            rest = {k: v for k, v in node.items() if k != "anyOf"}
            if len(variants) == 1:
                return clean({**variants[0], **rest})  # field-level keys (description) win
            return clean({**rest, "anyOf": variants})
        if "$ref" in node:  # inline the enum/nested def in place
            target = dict(defs.get(node["$ref"].split("/")[-1], {}))
            target.update({k: v for k, v in node.items() if k != "$ref"})
            return clean(target)
        return {k: clean(v) for k, v in node.items() if k not in _SCHEMA_DROP_KEYS}

    out = clean(raw)
    out.setdefault("type", "object")
    out.setdefault("properties", {})
    return out
