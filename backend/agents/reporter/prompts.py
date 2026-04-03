"""Prompt strings and builders for the generate agent and Gemini synthesis."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

# Google Ads weekly brief — system instructions (shared by LangChain + Gemini paths).
GOOGLE_ADS_WEEKLY_BRIEF_SYSTEM = """# Google Ads Weekly Brief Template

Use this template after the raw Google Ads data has already been normalized into
the `GoogleAdsBrief` schema contract.

## Job

Turn the structured Google Ads payload into a concise operator report.

The report must answer:

1. What changed?
2. Why does it matter?
3. What should the operator do next?

## Rules

- Use only the normalized payload provided.
- Do not invent platform data.
- Prefer concrete operator language over abstract marketing language.
- Make recommendations specific: scale, pause, monitor, refresh, tighten, or investigate.
- Focus on campaign-level decisions, not generic PPC advice.
- If evidence is weak, say so with lower confidence.

## Output Contract

Return:

- `narrative.verdict`
- `narrative.summary`
- `narrative.operator_takeaway`
- `highlights[]`
- `risks[]`
- `recommended_actions[]`

## Finding Style

Each finding should include:

- a short title
- 1-3 pieces of evidence from the data
- why it matters commercially
- a clear recommended action
- a confidence level

## Example Tone

Good:

- Brand search is carrying efficiency while two non-brand campaigns are burning spend without enough conversion value to justify their budget.
- Pause Campaign X this week unless conversion quality improves after targeting cleanup.
- CTR is falling, which points to likely creative fatigue rather than a bidding issue alone.

Bad:

- Performance was mixed overall.
- Consider optimizing campaigns.
- Some campaigns may need improvement.
"""

# ---------------------------------------------------------------------------
# Goal-specific analysis directives
# ---------------------------------------------------------------------------

GOAL_DIRECTIVES: Dict[str, str] = {
    "lower_cac": """## Goal-Specific Directive: Lower CAC

Focus your analysis on cost-per-acquisition reduction opportunities:
- Identify high-CPA search terms that should be added as negative keywords
- Flag device segments where CPA is significantly above the account average
- Look for campaigns or ad groups with high spend but low conversion rates
- Recommend specific budget shifts from high-CPA to low-CPA segments
- Quantify potential CPA savings from recommended changes
- Prioritize findings by potential CPA impact (largest savings first)
""",
    "maximize_roas": """## Goal-Specific Directive: Maximize ROAS

Focus your analysis on return-on-ad-spend optimization:
- Identify ad groups and campaigns with the highest ROAS potential
- Flag segments where ROAS is below 1.0x (losing money)
- Look for device/platform splits where ROAS varies significantly
- Recommend budget reallocation from low-ROAS to high-ROAS segments
- Identify campaigns where conversion value is disproportionate to spend
- Prioritize findings by potential ROAS improvement (largest gains first)
""",
    "scale_conversions": """## Goal-Specific Directive: Scale Conversions

Focus your analysis on conversion volume growth opportunities:
- Identify devices/regions with strong conversion rates but low impression share
- Flag geographic areas showing high conversion efficiency that could absorb more budget
- Look for campaigns converting well that may be limited by budget or bid caps
- Recommend specific geo or device bid adjustments to capture more volume
- Quantify potential conversion gains from recommended expansions
- Prioritize findings by incremental conversion potential
""",
    "audit_spend": """## Goal-Specific Directive: Audit Spend Efficiency

Focus your analysis on identifying and eliminating wasted spend:
- Identify search terms consuming budget with zero or near-zero conversions
- Flag ad groups with high spend but poor ROAS across the account
- Look for geographic areas draining budget without adequate returns
- Calculate total wasted spend and potential recovery from recommended cuts
- Recommend specific negative keywords, geo exclusions, and budget reallocations
- Prioritize findings by amount of spend at risk (largest waste first)
""",
}


def get_system_prompt(goal: str = "", context: str = "") -> str:
    """System instruction: weekly brief contract + optional goal/context + directives."""
    sections: list[str] = []
    if goal:
        sections.append(f"## User Goal\n{goal}")
    if context:
        sections.append(f"## Additional Context\n{context}")

    # Add goal-specific analysis directive
    goal_key = goal.lower().strip().replace(" ", "_").replace("-", "_")
    directive = GOAL_DIRECTIVES.get(goal_key, "")
    if not directive:
        # Try fuzzy match
        for key, value in GOAL_DIRECTIVES.items():
            if key in goal_key or goal_key in key:
                directive = value
                break
    if directive:
        sections.append(directive)

    sections.append(GOOGLE_ADS_WEEKLY_BRIEF_SYSTEM)
    return "\n\n".join(sections)


def get_synthesis_user_prompt(
    brief_dict: Dict[str, Any],
    raw_payload: Dict[str, Any],
    *,
    supplementary: Optional[Dict[str, Any]] = None,
) -> str:
    """User message with compact JSON payloads for synthesis.

    When supplementary data is available (from goal-driven tool calls),
    it's included as additional context for richer analysis.
    """
    compact_brief = json.dumps(brief_dict, separators=(",", ":"), default=str)[:120_000]
    compact_raw = json.dumps(raw_payload, separators=(",", ":"), default=str)[:120_000]

    parts = [
        "You output ONLY fields: narrative (verdict, summary, operator_takeaway), "
        "highlights, risks, recommended_actions. Match the JSON schema exactly. "
        "Use only data from the payloads; do not invent metrics.\n",
        f"Deterministic brief JSON:\n{compact_brief}\n",
        f"Raw campaign payload:\n{compact_raw}",
    ]

    if supplementary:
        parts.append(
            "\n\n--- Supplementary Data (goal-specific) ---\n"
            "The following additional data was fetched based on the user's goal. "
            "Use it to provide deeper, more actionable insights. Reference specific "
            "data points from these reports in your evidence fields.\n"
        )
        for tool_name, data in supplementary.items():
            compact = json.dumps(data, separators=(",", ":"), default=str)[:60_000]
            report_type = data.get("report_type", tool_name)
            row_count = data.get("row_count", "?")
            parts.append(f"\n{report_type} ({row_count} rows):\n{compact}")

    return "\n".join(parts)
