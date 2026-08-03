"""Guardrail enforcement — per-account learned invariants, checked in code.

The Gads engagement showed the safety layer must not live only in prose an
agent happens to read. Every change is checked against the account's active
guardrails at preview time (violations mark the change ``blocked``) and again
defensively at apply time.
"""

from __future__ import annotations

import json
from typing import Any

from models.execution import ExecutionGuardrail


def _matches(change: dict[str, Any], match: dict[str, Any]) -> bool:
    op_types = match.get("op_types") or []
    if op_types and change.get("op_type") not in op_types:
        return False
    needle = (match.get("target_contains") or "").strip()
    if needle:
        haystack = json.dumps(
            {"target": change.get("target"), "payload": change.get("payload")},
            default=str,
        )
        if needle not in haystack:
            return False
    # A matcher with neither op_types nor target_contains blocks nothing —
    # it is prose-only (still shown to agents/UI, never enforced blindly).
    if not op_types and not needle:
        return False
    return True


def violations_for(
    change: dict[str, Any], guardrails: list[ExecutionGuardrail]
) -> list[str]:
    """Rules (human statements) violated by this change."""
    return [g.rule for g in guardrails if g.active and _matches(change, g.match or {})]
