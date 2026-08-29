"""Prompt builders for the generate agent and synthesis phase.

Mode-dispatching: get_system_prompt() accepts a `mode` parameter and routes
to the appropriate protocol and goal directive. Per-request data
(business_context, the user goal, additional context) is rendered by
get_synthesis_user_prompt — NOT the system prompt — so the cached system prefix
stays byte-identical across customers and the Claude Agent SDK can reuse it.

Usage:
    from agents.insights.prompts import get_system_prompt, get_synthesis_user_prompt

    system = get_system_prompt(goal=goal, mode="organic_growth")
    user   = get_synthesis_user_prompt(
        all_briefs, supplementary=supp, business_context=biz,
        goal=goal, custom_goal=custom, context=ctx, mode="organic_growth",
    )
"""

from __future__ import annotations

import json
from typing import Any

from agents.core.context import format_business_context, format_user_context
from agents.insights.catalog import get_catalogs_for_connectors
from agents.insights.catalog.prompt import entity_catalog_prompt_block
from agents.insights.goals.paid_ads import goal_heading_text as paid_goal_heading
from agents.insights.goals.organic_growth import goal_heading_text as organic_goal_heading


def _goal_heading(goal: Any, custom_goal: str, mode: str) -> str:
    if mode == "organic_growth":
        return organic_goal_heading(goal, custom_goal=custom_goal)
    return paid_goal_heading(goal, custom_goal=custom_goal)


# Generic, user-agnostic directive — byte-identical for every user, so it lives
# safely in the cached system prefix. The actual reader (name/role/…) is supplied
# per-request in the <user_context> block of the user message.
_READER_DIRECTIVE = (
    "When a <user_context> block is present in the request, tailor the depth, "
    "framing, and vocabulary of your analysis to that reader (e.g. a founder, a "
    "CMO, or a hands-on specialist) — without changing the underlying findings, "
    "the numbers you cite, or the required output structure."
)


def get_system_prompt(
    *,
    goal: Any = None,
    mode: str = "paid_ads",
) -> str:
    """Assemble the **cache-stable** system instruction for synthesis.

    Contains only content that is identical across customers for a given
    (mode, goal): persona, the mode-specific protocols, the categorical goal
    directive, and the confidentiality guardrail. Per-request data
    (business_context, the free-text user goal, additional context) is rendered
    by get_synthesis_user_prompt instead — keeping this string byte-identical so
    the Claude Agent SDK reuses the cached system prefix across runs. Putting
    per-customer data here would give every customer a distinct cached prefix and
    defeat caching of the large protocol blocks.
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

    _persona = (
        "You are Duct's growth marketing analyst — a world-class paid-ads and "
        "organic-growth expert who turns raw marketing data into clear, "
        "decision-ready insight for operators."
    )
    sections: list[str] = [_persona, ANALYSIS_PROTOCOL, DASHBOARD_LAYOUT_PROTOCOL]

    # Categorical goal directive — stable per goal, so it's safe to keep in the
    # cached system prefix (unlike the free-text user goal, which lives in the
    # user message via get_synthesis_user_prompt).
    if goal is not None:
        directive = directives.get(goal, "")
        if directive:
            sections.append(directive)

    # Static reader-personalisation directive (cache-safe — same for everyone);
    # the per-user value travels in <user_context> in the user message.
    sections.append(_READER_DIRECTIVE)

    from agents.core.persona import with_confidentiality
    return with_confidentiality("\n\n".join(sections))


def get_synthesis_user_prompt(
    all_briefs: dict[str, Any],
    raw_payload: dict[str, Any] | None = None,  # legacy compat: (brief_dict, raw_payload)
    *,
    supplementary: dict[str, Any] | None = None,
    mode: str = "paid_ads",
    business_context: dict[str, Any] | None = None,
    user_context: dict[str, Any] | None = None,
    goal: Any = None,
    custom_goal: str = "",
    context: str = "",
    memory: str = "",
) -> str:
    """User message with per-request context + connector data payloads.

    Follows Gemini best practice: all context/data FIRST, task instruction LAST.
    Per-request context (business_context, the user goal, additional context) is
    rendered here rather than in the system prompt so the cached system prefix
    stays byte-identical across customers — see get_system_prompt. Each connector
    brief is labelled by its connector ID; each supplementary dataset gets
    mode-specific analysis instructions alongside the data.

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

    parts: list[str] = []

    # Per-request context FIRST — kept out of the system prompt so the cached
    # system prefix stays byte-identical across customers (see get_system_prompt).
    biz_section = format_business_context(
        business_context,
        include_paid=(mode != "organic_growth"),
        include_organic=(mode == "organic_growth"),
    )
    if biz_section:
        parts.append(biz_section)
    user_section = format_user_context(user_context)
    if user_section:
        parts.append(user_section)
    if goal is not None:
        parts.append(f"<user_goal>\n{_goal_heading(goal, custom_goal, mode)}\n</user_goal>")
    if context:
        parts.append(f"<additional_context>\n{context}\n</additional_context>")
    # Project memory, pre-rendered by service/memory.py (it carries its own
    # citation rules). Here rather than in the system prompt for the same reason
    # as everything else in this function: the cached system prefix must stay
    # byte-identical across customers.
    if memory:
        parts.append(memory)

    parts.append("<data>\n")

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
