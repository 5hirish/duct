"""Prompt builders for the generate agent and synthesis phase.

Mode-dispatching: get_system_prompt() accepts a `mode` parameter and routes
to the appropriate protocol, directives, and business context formatter.

Usage:
    from agents.insights.prompts import get_system_prompt, get_synthesis_user_prompt

    system = get_system_prompt(goal=goal, context=ctx, business_context=biz, mode="organic_growth")
    user   = get_synthesis_user_prompt(all_briefs, supplementary=supp)
"""

from __future__ import annotations

import json
from typing import Any

from agents.core.context import format_business_context
from agents.insights.catalog import get_catalogs_for_connectors
from agents.insights.catalog.prompt import entity_catalog_prompt_block
from agents.insights.goals.paid_ads import goal_heading_text as paid_goal_heading
from agents.insights.goals.organic_growth import goal_heading_text as organic_goal_heading


def _goal_heading(goal: Any, custom_goal: str, mode: str) -> str:
    if mode == "organic_growth":
        return organic_goal_heading(goal, custom_goal=custom_goal)
    return paid_goal_heading(goal, custom_goal=custom_goal)


def get_system_prompt(
    *,
    goal: Any = None,
    custom_goal: str = "",
    context: str = "",
    business_context: dict[str, Any] | None = None,
    mode: str = "paid_ads",
) -> str:
    """Assemble the system instruction for the synthesis phase.

    Dispatches to the mode-specific protocol, directives, and business context
    formatter. Follows Gemini best practice: role and constraints first, then
    context, then goal-specific directive.
    """
    if mode == "organic_growth":
        from agents.insights.prompts.organic_growth import (
            ANALYSIS_PROTOCOL,
            DASHBOARD_LAYOUT_PROTOCOL,
        )
        from agents.insights.goals.organic_growth import GOAL_DIRECTIVES
        directives = GOAL_DIRECTIVES
    else:
        from agents.insights.prompts.paid_ads import (
            ANALYSIS_PROTOCOL,
            DASHBOARD_LAYOUT_PROTOCOL,
        )
        from agents.insights.goals.paid_ads import GOAL_DIRECTIVES
        directives = GOAL_DIRECTIVES

    sections: list[str] = [ANALYSIS_PROTOCOL, DASHBOARD_LAYOUT_PROTOCOL]

    # Shared business-context formatter (agents/core/context.py) — one
    # standard <business_context> block across all agents; mode selects section.
    biz_section = format_business_context(
        business_context,
        include_paid=(mode != "organic_growth"),
        include_organic=(mode == "organic_growth"),
    )
    if biz_section:
        sections.append(biz_section)

    if goal is not None:
        heading = _goal_heading(goal, custom_goal, mode)
        sections.append(f"<user_goal>\n{heading}\n</user_goal>")

    if context:
        sections.append(f"<additional_context>\n{context}\n</additional_context>")

    if goal is not None:
        directive = directives.get(goal, "")
        if directive:
            sections.append(directive)

    return "\n\n".join(sections)


def get_synthesis_user_prompt(
    all_briefs: dict[str, Any],
    raw_payload: dict[str, Any] | None = None,  # legacy compat: (brief_dict, raw_payload)
    *,
    supplementary: dict[str, Any] | None = None,
    mode: str = "paid_ads",
) -> str:
    """User message with connector data payloads for synthesis.

    Follows Gemini best practice: all data/context FIRST, task instruction LAST.
    Each connector brief is labelled by its connector ID. Each supplementary
    dataset gets mode-specific analysis instructions alongside the data.

    New calling convention:
        all_briefs = {"gsc": {"brief": {...}, "raw": {...}}, "ga4": {...}}

    Legacy calling convention (brief.py backward compat):
        all_briefs = flat_brief_dict, raw_payload = raw_dict
        → wrapped automatically as {"connector": {"brief": ..., "raw": ...}}
    """
    # Detect legacy 2-arg call: all_briefs is a flat brief dict, raw_payload is the raw
    if raw_payload is not None:
        all_briefs = {"connector": {"brief": all_briefs, "raw": raw_payload}}
    if mode == "organic_growth":
        from agents.insights.prompts.organic_growth import SUPPLEMENTARY_ANALYSIS_GUIDES
    else:
        from agents.insights.prompts.paid_ads import SUPPLEMENTARY_ANALYSIS_GUIDES

    parts = ["<data>\n"]

    catalogs = get_catalogs_for_connectors(list(all_briefs.keys()))
    catalog_block = entity_catalog_prompt_block(catalogs)
    if catalog_block:
        parts.append(catalog_block)

    for connector_id, connector_data in all_briefs.items():
        # Support both {"brief": ..., "raw": ...} and flat brief dict
        if isinstance(connector_data, dict) and "brief" in connector_data:
            brief_dict = connector_data["brief"]
            raw_dict = connector_data.get("raw")
        else:
            brief_dict = connector_data
            raw_dict = None

        compact_brief = json.dumps(brief_dict, separators=(",", ":"), default=str)[:120_000]
        parts.append(f'<connector id="{connector_id}">')
        parts.append(f"<brief>\n{compact_brief}\n</brief>")
        if raw_dict:
            compact_raw = json.dumps(raw_dict, separators=(",", ":"), default=str)[:120_000]
            parts.append(f"<raw>\n{compact_raw}\n</raw>")
        parts.append("</connector>")

    if supplementary:
        parts.append("\n<supplementary_data>")
        for tool_name, data in supplementary.items():
            report_type = data.get("report_type", tool_name)
            row_count = data.get("row_count", "?")

            guide = SUPPLEMENTARY_ANALYSIS_GUIDES.get(report_type, "")
            if not guide:
                guide = SUPPLEMENTARY_ANALYSIS_GUIDES.get(tool_name.replace("fetch_", ""), "")

            compact = json.dumps(data, separators=(",", ":"), default=str)[:60_000]
            header = f'\n<dataset type="{report_type}" rows="{row_count}">'
            if guide:
                parts.append(f"{header}\n{guide}\n\n{compact}\n</dataset>")
            else:
                parts.append(f"{header}\n{compact}\n</dataset>")
        parts.append("\n</supplementary_data>")

    parts.append("\n</data>")

    parts.append(
        "\n\n<task>\n"
        "Based on all the data above, produce your structured analysis.\n"
        "Cross-reference supplementary data with connector performance.\n"
        "Cite specific numbers in every finding. Follow the analysis protocol.\n"
        "Remember to run the self-critique checklist before finalizing.\n"
        "</task>"
    )

    return "\n".join(parts)
