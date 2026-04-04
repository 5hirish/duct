"""Prompt strings and builders for the generate agent and Gemini synthesis."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from agents.reporter.goals import GOAL_DIRECTIVES, ReportGenerationGoal, goal_heading_text

# ---------------------------------------------------------------------------
# Analysis protocol — the core prompt that turns the LLM from polisher to
# reasoner. Follows the nomadtools barrio/thoughtpolice pattern of encoding
# multi-step reasoning directly in the prompt structure.
# ---------------------------------------------------------------------------

ANALYSIS_PROTOCOL = """## Identity

You are a senior paid media analyst producing an operator brief.
You receive a deterministic baseline analysis plus raw and supplementary data.
Your job is to reason through the data, validate or override baseline classifications,
cross-reference data sources, and produce findings backed by specific evidence chains.

## Analysis Protocol

1. READ the deterministic brief classifications. These are your baseline — do not discard them,
   but treat them as a starting point, not gospel.

2. FOR EACH campaign, evaluate whether the baseline classification makes sense given business context:
   - A $200 CPA classified as "pause" may be correct for ecommerce but wrong for enterprise SaaS with $50k ACV
   - A 2.0x ROAS classified as "refine" may deserve "scale" if the account is new and still learning
   - A "monitor" campaign consuming 40% of budget deserves closer scrutiny regardless of ROAS
   - If you disagree with a classification, add a classification_override with your reasoning

3. CROSS-REFERENCE supplementary data with campaign performance:
   - If search terms are present: identify which specific queries inflate CPA on underperforming campaigns
   - If device data is present: check whether one device segment is dragging down an otherwise healthy campaign
   - If geo data is present: look for geographic concentration issues or untapped expansion opportunities
   - If ad group data is present: determine whether one ad group is dragging the parent campaign classification

4. BUILD evidence chains for each finding — be specific, not generic:
   NOT: "Campaign X has high CPA"
   BUT: "Campaign X CPA is $180 vs target $50, driven by mobile CPA of $340 (3x desktop)
         and search term 'free trial' consuming 22% of spend with 0 conversions"
   Each evidence_chain should name the primary_metric, list contributing_factors from
   supplementary data, and note which data_sources_used.

5. PRODUCE findings, overrides, and recommended actions. Prioritize by goal impact.
   Each recommended action should be concrete enough to execute this week.

## Output Rules

- Use only data from the payloads; do not invent metrics.
- Each finding must include specific evidence from the data.
- Prefer concrete operator language over abstract marketing language.
- Make recommendations specific: scale, pause, monitor, refresh, refine, or investigate.
- If evidence is weak, say so with lower confidence.
- Use analysis_notes to summarize your reasoning process (1-2 sentences).

## Finding Style

Each finding should include:

- a short title
- 1-3 pieces of evidence from the data
- an evidence_chain linking supplementary data to the finding
- why it matters commercially
- a clear recommended action
- a confidence level

## Example Tone

Good:

- Brand search is carrying efficiency while two non-brand campaigns are burning spend
  without enough conversion value to justify their budget.
- Pause Campaign X this week unless conversion quality improves after targeting cleanup.
- CTR is falling on mobile specifically, which points to creative fatigue on small screens
  rather than a bidding issue.

Bad:

- Performance was mixed overall.
- Consider optimizing campaigns.
- Some campaigns may need improvement.
"""

# ---------------------------------------------------------------------------
# Per-dataset analysis guides — injected alongside supplementary data so the
# LLM knows exactly what to look for in each data slice.
# ---------------------------------------------------------------------------

SUPPLEMENTARY_ANALYSIS_GUIDES: Dict[str, str] = {
    "search_terms": (
        "ANALYZE search terms by:\n"
        "- Identify terms consuming >5% of campaign spend with 0 conversions — these are negative keyword candidates\n"
        "- Identify terms with ROAS >2x account average — these are expansion candidates\n"
        "- Flag broad match terms bleeding into irrelevant queries\n"
        "- Cross-reference: for each underperforming campaign, which specific search terms are inflating its CPA?\n"
        "- Quantify wasted spend on non-converting terms"
    ),
    "device_performance": (
        "ANALYZE device splits by:\n"
        "- For each campaign, compare device CPA (mobile vs desktop vs tablet)\n"
        "- Flag campaigns where one device has CPA >2x another — these need bid adjustments\n"
        "- Check if mobile is dragging down an otherwise healthy campaign's overall metrics\n"
        "- Cross-reference: does the high-CPA device also have lower CTR (creative issue) or lower conv rate (landing page issue)?\n"
        "- Identify devices where conversion volume is strong but budget is limited"
    ),
    "geo_performance": (
        "ANALYZE geographic data by:\n"
        "- Identify regions with spend but 0 conversions — geo exclusion candidates\n"
        "- Identify regions with strong ROAS but low impression share — expansion candidates\n"
        "- Flag regions where CPA is >2x account average\n"
        "- Cross-reference: do underperforming campaigns have geographic concentration issues?\n"
        "- Quantify spend in non-converting regions as potential savings"
    ),
    "ad_group_performance": (
        "ANALYZE ad groups by:\n"
        "- Within each campaign, find ad groups consuming >30% of spend with below-average ROAS\n"
        "- Identify ad groups with strong conversion rates that could absorb more budget\n"
        "- Flag ad groups where the parent campaign looks 'mixed' because one ad group drags it down\n"
        "- Cross-reference: would pausing one ad group change the campaign-level classification?\n"
        "- Look for ad groups with declining performance that may indicate creative fatigue"
    ),
}


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _format_business_context(biz_ctx: Dict[str, Any] | None) -> str:
    """Format business context into a prompt section. Omits empty/zero fields."""
    if not biz_ctx:
        return ""

    lines = []
    if biz_ctx.get("industry"):
        lines.append(f"- Industry: {biz_ctx['industry']}")
    if biz_ctx.get("monthly_budget"):
        lines.append(f"- Monthly ad budget: ${biz_ctx['monthly_budget']:,.0f}")
    if biz_ctx.get("target_cpa"):
        lines.append(f"- Target CPA: ${biz_ctx['target_cpa']:,.2f}")
    if biz_ctx.get("target_roas"):
        lines.append(f"- Target ROAS: {biz_ctx['target_roas']:.1f}x")
    if biz_ctx.get("notes"):
        lines.append(f"- Notes: {biz_ctx['notes']}")

    if not lines:
        return ""
    return "## Business Context\n\n" + "\n".join(lines)


def get_system_prompt(
    *,
    goal: ReportGenerationGoal | None = None,
    custom_goal: str = "",
    context: str = "",
    business_context: Dict[str, Any] | None = None,
) -> str:
    """System instruction: analysis protocol + business context + goal directive."""
    sections: list[str] = [ANALYSIS_PROTOCOL]

    biz_section = _format_business_context(business_context)
    if biz_section:
        sections.append(biz_section)

    if goal is not None:
        heading = goal_heading_text(goal, custom_goal=custom_goal)
        sections.append(f"## User Goal\n\n{heading}")

    if context:
        sections.append(f"## Additional Context\n\n{context}")

    if goal is not None:
        directive = GOAL_DIRECTIVES.get(goal, "")
        if directive:
            sections.append(directive)

    return "\n\n".join(sections)


def get_synthesis_user_prompt(
    brief_dict: Dict[str, Any],
    raw_payload: Dict[str, Any],
    *,
    supplementary: Optional[Dict[str, Any]] = None,
) -> str:
    """User message with compact JSON payloads for synthesis.

    When supplementary data is available (from goal-driven tool calls),
    each dataset gets specific analysis instructions alongside the data.
    """
    compact_brief = json.dumps(brief_dict, separators=(",", ":"), default=str)[:120_000]
    compact_raw = json.dumps(raw_payload, separators=(",", ":"), default=str)[:120_000]

    parts = [
        "Use only data from the payloads; do not invent metrics.\n",
        f"Deterministic brief JSON:\n{compact_brief}\n",
        f"Raw campaign payload:\n{compact_raw}",
    ]

    if supplementary:
        parts.append(
            "\n\n--- Supplementary Data (goal-specific) ---\n"
            "The following additional data was fetched based on the user's goal. "
            "Use it to provide deeper, more actionable insights. Reference specific "
            "data points from these reports in your evidence_chain fields.\n"
        )
        for tool_name, data in supplementary.items():
            report_type = data.get("report_type", tool_name)
            row_count = data.get("row_count", "?")

            # Inject per-dataset analysis guide
            guide = SUPPLEMENTARY_ANALYSIS_GUIDES.get(report_type, "")
            if not guide:
                guide = SUPPLEMENTARY_ANALYSIS_GUIDES.get(tool_name.replace("fetch_", ""), "")

            compact = json.dumps(data, separators=(",", ":"), default=str)[:60_000]
            header = f"\n### {report_type} ({row_count} rows)"
            if guide:
                parts.append(f"{header}\n\n{guide}\n\nData:\n{compact}")
            else:
                parts.append(f"{header}\n\nData:\n{compact}")

    return "\n".join(parts)
