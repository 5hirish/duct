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

from agents.insights.tools import CONNECTOR_BY_TOOL


# ---------------------------------------------------------------------------
# Descriptions copied verbatim from v1/tools.py
# ---------------------------------------------------------------------------

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "fetch_campaign_performance": (
        "Fetch Google Ads campaign performance data. Returns per-campaign "
        "spend, clicks, impressions, conversions, ROAS, and previous-period "
        "comparison. Use this as the primary data source for any analysis."
    ),
    "fetch_search_terms": (
        "Fetch the top 100 search terms by spend. Shows which actual user "
        "queries triggered ads, their match type, and per-term spend, CTR, "
        "conversions, CPA, and ROAS. Essential for finding wasted spend on "
        "irrelevant queries and identifying high-value terms to target."
    ),
    "fetch_device_performance": (
        "Fetch campaign performance broken down by device (MOBILE, DESKTOP, "
        "TABLET). Reveals device-level efficiency gaps — e.g. high CPA on "
        "mobile vs desktop. Use to find budget reallocation opportunities "
        "across devices."
    ),
    "fetch_geo_performance": (
        "Fetch geographic performance data showing spend, conversions, and "
        "ROAS by location. Reveals which regions are converting efficiently "
        "and which are wasting budget. Use to identify geo expansion or "
        "geo exclusion opportunities."
    ),
    "fetch_ad_group_performance": (
        "Fetch ad group level performance within campaigns. Shows which "
        "specific ad groups drive conversions vs waste spend. Deeper "
        "granularity than campaign-level data. Use to find optimization "
        "opportunities within campaigns that look mixed at the campaign level."
    ),
    "fetch_ga4_landing_pages": (
        "Fetch GA4 landing page behavior for paid traffic (google / cpc), "
        "including sessions, bounce rate, engagement rate, session duration, "
        "conversions, and revenue."
    ),
    "fetch_ga4_conversion_paths": (
        "Fetch GA4 conversion path context by source/medium and channel group "
        "to evaluate assisted-conversion dynamics beyond last-click."
    ),
    "fetch_gsc_query_performance": (
        "Fetch Google Search Console organic query performance with clicks, "
        "impressions, CTR, and position for overlap analysis against paid terms."
    ),
    "fetch_gsc_page_performance": (
        "Fetch Google Search Console organic page performance with clicks, "
        "impressions, CTR, and position for page-level organic/paid alignment."
    ),
}


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
