"""LangChain tool definitions for the generate agent.

Each Google Ads data slice is a separate StructuredTool. The agent receives
only the tools relevant to the user's goal — it decides which to call.

Credential closure pattern: auth params are baked into the fetch function
at registration time. Only customer_id, date_from, date_to are exposed to
the LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.reporter.goals import ReportGenerationGoal


# ---------------------------------------------------------------------------
# Shared input schema — all supplementary tools take the same params
# ---------------------------------------------------------------------------

class GoogleAdsFetchInput(BaseModel):
    """Input schema for Google Ads fetch tools."""

    customer_id: str = Field(description="Google Ads customer ID (digits only, no dashes)")
    date_from: str = Field(description="Start date in YYYY-MM-DD format")
    date_to: str = Field(description="End date in YYYY-MM-DD format")


# ---------------------------------------------------------------------------
# Tool factory helper
# ---------------------------------------------------------------------------

def _make_tool(
    fetch_fn: Callable[..., dict[str, Any]],
    name: str,
    description: str,
) -> StructuredTool:
    """Wrap a pre-credentialed fetch function as a LangChain StructuredTool."""

    def _wrapper(**kwargs: Any) -> dict[str, Any]:
        validated = GoogleAdsFetchInput(**kwargs)
        return fetch_fn(
            customer_id=validated.customer_id,
            date_from=validated.date_from,
            date_to=validated.date_to,
        )

    return StructuredTool.from_function(
        func=_wrapper,
        name=name,
        description=description,
        args_schema=GoogleAdsFetchInput,
    )


# ---------------------------------------------------------------------------
# Individual tool creators
# ---------------------------------------------------------------------------

def create_campaign_performance_tool(
    fetch_fn: Callable[..., dict[str, Any]],
) -> StructuredTool:
    """Campaign-level performance (base data, always available)."""
    return _make_tool(
        fetch_fn,
        name="fetch_campaign_performance",
        description=(
            "Fetch Google Ads campaign performance data. Returns per-campaign "
            "spend, clicks, impressions, conversions, ROAS, and previous-period "
            "comparison. Use this as the primary data source for any analysis."
        ),
    )


def create_search_terms_tool(
    fetch_fn: Callable[..., dict[str, Any]],
) -> StructuredTool:
    """Search term report — reveals which queries trigger ads."""
    return _make_tool(
        fetch_fn,
        name="fetch_search_terms",
        description=(
            "Fetch the top 100 search terms by spend. Shows which actual user "
            "queries triggered ads, their match type, and per-term spend, CTR, "
            "conversions, CPA, and ROAS. Essential for finding wasted spend on "
            "irrelevant queries and identifying high-value terms to target."
        ),
    )


def create_device_performance_tool(
    fetch_fn: Callable[..., dict[str, Any]],
) -> StructuredTool:
    """Campaign x device segmentation (MOBILE, DESKTOP, TABLET)."""
    return _make_tool(
        fetch_fn,
        name="fetch_device_performance",
        description=(
            "Fetch campaign performance broken down by device (MOBILE, DESKTOP, "
            "TABLET). Reveals device-level efficiency gaps — e.g. high CPA on "
            "mobile vs desktop. Use to find budget reallocation opportunities "
            "across devices."
        ),
    )


def create_geo_performance_tool(
    fetch_fn: Callable[..., dict[str, Any]],
) -> StructuredTool:
    """Geographic performance by country/region."""
    return _make_tool(
        fetch_fn,
        name="fetch_geo_performance",
        description=(
            "Fetch geographic performance data showing spend, conversions, and "
            "ROAS by location. Reveals which regions are converting efficiently "
            "and which are wasting budget. Use to identify geo expansion or "
            "geo exclusion opportunities."
        ),
    )


def create_ad_group_performance_tool(
    fetch_fn: Callable[..., dict[str, Any]],
) -> StructuredTool:
    """Ad group level detail — deeper than campaign."""
    return _make_tool(
        fetch_fn,
        name="fetch_ad_group_performance",
        description=(
            "Fetch ad group level performance within campaigns. Shows which "
            "specific ad groups drive conversions vs waste spend. Deeper "
            "granularity than campaign-level data. Use to find optimization "
            "opportunities within campaigns that look mixed at the campaign level."
        ),
    )


# ---------------------------------------------------------------------------
# Goal → tool mapping
# ---------------------------------------------------------------------------

# All supplementary tools available to any goal. The LLM decides which to call.
ALL_TOOL_NAMES: list[str] = [
    "fetch_search_terms",
    "fetch_device_performance",
    "fetch_geo_performance",
    "fetch_ad_group_performance",
]

# Priority hints per goal — marked [PRIORITY] in the Phase 1 prompt so the
# LLM knows which tools are most likely useful, but it can call any tool.
GOAL_TOOL_PRIORITIES: dict[ReportGenerationGoal, list[str]] = {
    ReportGenerationGoal.LOWER_CAC: [
        "fetch_search_terms",
        "fetch_device_performance",
    ],
    ReportGenerationGoal.MAXIMIZE_ROAS: [
        "fetch_ad_group_performance",
        "fetch_device_performance",
    ],
    ReportGenerationGoal.SCALE_CONVERSIONS: [
        "fetch_device_performance",
        "fetch_geo_performance",
    ],
    ReportGenerationGoal.AUDIT_SPEND: [
        "fetch_search_terms",
        "fetch_ad_group_performance",
        "fetch_geo_performance",
    ],
    ReportGenerationGoal.CUSTOM: [
        "fetch_ad_group_performance",
    ],
}


def get_tool_names_for_goal(goal: ReportGenerationGoal) -> list[str]:
    """Return ALL supplementary tool names. The LLM decides which to call."""
    return list(ALL_TOOL_NAMES)
