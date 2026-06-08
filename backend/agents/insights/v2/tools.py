"""ADK tool wrappers for supplementary data fetching.

ADK auto-wraps typed Python functions as tools — no StructuredTool or
args_schema needed. Tool descriptions are copied verbatim from v1/tools.py
so the LLM sees identical guidance regardless of engine.

Three connector types have different required params:
- Google Ads: customer_id, date_from, date_to
- GA4:        property_id, date_from, date_to
- GSC:        site_url, date_from, date_to
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.insights.tools import CONNECTOR_BY_TOOL, TOOL_DESCRIPTIONS

# Tool descriptions are single-sourced in agents/insights/tools.py so the LLM
# sees identical guidance regardless of engine (v1/v2/v3).
_TOOL_DESCRIPTIONS = TOOL_DESCRIPTIONS


# ---------------------------------------------------------------------------
# Tool factory helpers
# ---------------------------------------------------------------------------

def _make_google_ads_tool(
    name: str,
    description: str,
    fetch_fn: Callable[..., dict[str, Any]],
) -> Callable:
    """Wrap a pre-credentialed Google Ads fetch fn as an ADK-compatible tool."""

    def tool_impl(customer_id: str, date_from: str, date_to: str) -> dict:
        return fetch_fn(customer_id=customer_id, date_from=date_from, date_to=date_to)

    tool_impl.__name__ = name
    tool_impl.__doc__ = description
    return tool_impl


def _make_ga4_tool(
    name: str,
    description: str,
    fetch_fn: Callable[..., dict[str, Any]],
) -> Callable:
    """Wrap a pre-credentialed GA4 fetch fn as an ADK-compatible tool."""

    def tool_impl(property_id: str, date_from: str, date_to: str) -> dict:
        return fetch_fn(property_id=property_id, date_from=date_from, date_to=date_to)

    tool_impl.__name__ = name
    tool_impl.__doc__ = description
    return tool_impl


def _make_gsc_tool(
    name: str,
    description: str,
    fetch_fn: Callable[..., dict[str, Any]],
) -> Callable:
    """Wrap a pre-credentialed GSC fetch fn as an ADK-compatible tool."""

    def tool_impl(site_url: str, date_from: str, date_to: str) -> dict:
        return fetch_fn(site_url=site_url, date_from=date_from, date_to=date_to)

    tool_impl.__name__ = name
    tool_impl.__doc__ = description
    return tool_impl


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_adk_tools_for_goal(
    goal_tool_names: list[str],
    fetch_fns: dict[str, Callable[..., dict[str, Any]]],
) -> list[Callable]:
    """Build ADK-compatible tool callables for a specific set of tool names."""
    tools: list[Callable] = []
    for name in goal_tool_names:
        fn = fetch_fns.get(name)
        if not fn:
            continue
        description = _TOOL_DESCRIPTIONS.get(name, f"Fetch {name} data.")
        connector = CONNECTOR_BY_TOOL.get(name, "google_ads")
        if connector == "ga4":
            tools.append(_make_ga4_tool(name, description, fn))
        elif connector == "gsc":
            tools.append(_make_gsc_tool(name, description, fn))
        else:
            tools.append(_make_google_ads_tool(name, description, fn))
    return tools
