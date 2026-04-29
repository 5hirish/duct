"""Structured supplementary tool registry and request-time selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    connector_id: str
    description_short: str
    description_long: str
    goal_relevance: dict[str, int]
    creator_fn: Any


_REGISTRY: dict[str, ToolSpec] = {}


def add_tool(spec: ToolSpec) -> None:
    _REGISTRY[spec.name] = spec


def get_registry() -> dict[str, ToolSpec]:
    return dict(_REGISTRY)


def get_tools_for_request(
    *,
    goal: str,
    available_tool_names: list[str],
    allowlist: list[str] | None = None,
    max_tools: int = 8,
) -> list[ToolSpec]:
    """Select the most relevant tools for a specific request."""
    available_set = set(available_tool_names)
    allowlist_set = set(allowlist or available_tool_names)
    candidates = [
        spec
        for name, spec in _REGISTRY.items()
        if name in available_set and name in allowlist_set
    ]
    scored = sorted(
        candidates,
        key=lambda spec: (spec.goal_relevance.get(goal, 0), spec.name),
        reverse=True,
    )
    return scored[:max_tools]
