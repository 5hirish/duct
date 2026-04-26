"""Paid Ads insight goals — enum, labels, directives, and tool priorities."""

from __future__ import annotations

from enum import StrEnum


class InsightGenerationGoal(StrEnum):
    LOWER_CAC = "lower_cac"
    MAXIMIZE_ROAS = "maximize_roas"
    SCALE_CONVERSIONS = "scale_conversions"
    AUDIT_SPEND = "audit_spend"
    CUSTOM = "custom"


GOAL_LABELS: dict[InsightGenerationGoal, str] = {
    InsightGenerationGoal.LOWER_CAC: "Lower CAC",
    InsightGenerationGoal.MAXIMIZE_ROAS: "Maximize ROAS",
    InsightGenerationGoal.SCALE_CONVERSIONS: "Scale conversions",
    InsightGenerationGoal.AUDIT_SPEND: "Audit spend efficiency",
    InsightGenerationGoal.CUSTOM: "Custom goal",
}

GOAL_DESCRIPTIONS: dict[InsightGenerationGoal, str] = {
    InsightGenerationGoal.LOWER_CAC: "Find which campaigns and audiences deliver the cheapest conversions — cut waste, keep quality.",
    InsightGenerationGoal.MAXIMIZE_ROAS: "Identify top-returning campaigns and reallocate budget away from underperformers.",
    InsightGenerationGoal.SCALE_CONVERSIONS: "Grow conversion volume while keeping cost efficiency in check — find headroom to spend more.",
    InsightGenerationGoal.AUDIT_SPEND: "Spot wasted budget, flag underperformers, and surface reallocation opportunities across campaigns.",
    InsightGenerationGoal.CUSTOM: "Describe your own analysis goal — the AI agent will tailor the insight to your intent.",
}

GOAL_ICONS: dict[InsightGenerationGoal, str] = {
    InsightGenerationGoal.LOWER_CAC: "📉",
    InsightGenerationGoal.MAXIMIZE_ROAS: "💰",
    InsightGenerationGoal.SCALE_CONVERSIONS: "🚀",
    InsightGenerationGoal.AUDIT_SPEND: "🔍",
    InsightGenerationGoal.CUSTOM: "✏️",
}

# Analysis directives keyed by goal — injected into system prompt.
GOAL_DIRECTIVES: dict[InsightGenerationGoal, str] = {
    InsightGenerationGoal.LOWER_CAC: """## Goal-Specific Directive: Lower CAC

Focus your analysis on cost-per-acquisition reduction opportunities:
- Identify high-CPA search terms that should be added as negative keywords
- Flag device segments where CPA is significantly above the account average
- Look for campaigns or ad groups with high spend but low conversion rates
- Use GA4 landing-page behavior to find paid traffic that bounces quickly
- Use GSC query overlap to reduce paid spend where organic already performs strongly
- Recommend specific budget shifts from high-CPA to low-CPA segments
- Quantify potential CPA savings from recommended changes
- Prioritize findings by potential CPA impact (largest savings first)
""",
    InsightGenerationGoal.MAXIMIZE_ROAS: """## Goal-Specific Directive: Maximize ROAS

Focus your analysis on return-on-ad-spend optimization:
- Identify ad groups and campaigns with the highest ROAS potential
- Flag segments where ROAS is below 1.0x (losing money)
- Look for device/platform splits where ROAS varies significantly
- Use GA4 conversion-path context before pausing campaigns with weak last-click ROAS
- Use GA4 landing-page engagement to separate traffic-quality issues from bid issues
- Recommend budget reallocation from low-ROAS to high-ROAS segments
- Identify campaigns where conversion value is disproportionate to spend
- Prioritize findings by potential ROAS improvement (largest gains first)
""",
    InsightGenerationGoal.SCALE_CONVERSIONS: """## Goal-Specific Directive: Scale Conversions

Focus your analysis on conversion volume growth opportunities:
- Identify devices/regions with strong conversion rates but low impression share
- Flag geographic areas showing high conversion efficiency that could absorb more budget
- Look for campaigns converting well that may be limited by budget or bid caps
- Use GA4 landing-page data to identify pages that can absorb more paid traffic
- Use GSC query/page data to find organic gaps where paid expansion can drive incremental conversions
- Recommend specific geo or device bid adjustments to capture more volume
- Quantify potential conversion gains from recommended expansions
- Prioritize findings by incremental conversion potential
""",
    InsightGenerationGoal.AUDIT_SPEND: """## Goal-Specific Directive: Audit Spend Efficiency

Focus your analysis on identifying and eliminating wasted spend:
- Identify search terms consuming budget with zero or near-zero conversions
- Flag ad groups with high spend but poor ROAS across the account
- Look for geographic areas draining budget without adequate returns
- Use GA4 landing-page behavior to identify campaigns paying for low-quality sessions
- Use GSC overlap to flag paid clicks likely cannibalizing strong organic visibility
- Calculate total wasted spend and potential recovery from recommended cuts
- Recommend specific negative keywords, geo exclusions, and budget reallocations
- Prioritize findings by amount of spend at risk (largest waste first)
""",
    InsightGenerationGoal.CUSTOM: """## Goal-Specific Directive: Custom objective

Address the user's stated objective using only the supplied data.
Prioritize concrete, measurable recommendations aligned with their wording.
""",
}

# Tool names to mark [PRIORITY] in the Phase 1 prompt per goal.
GOAL_TOOL_PRIORITIES: dict[InsightGenerationGoal, list[str]] = {
    InsightGenerationGoal.LOWER_CAC: [
        "fetch_search_terms",
        "fetch_device_performance",
        "fetch_ga4_landing_pages",
        "fetch_gsc_query_performance",
    ],
    InsightGenerationGoal.MAXIMIZE_ROAS: [
        "fetch_ad_group_performance",
        "fetch_device_performance",
        "fetch_ga4_conversion_paths",
    ],
    InsightGenerationGoal.SCALE_CONVERSIONS: [
        "fetch_device_performance",
        "fetch_geo_performance",
        "fetch_ga4_landing_pages",
        "fetch_gsc_query_performance",
    ],
    InsightGenerationGoal.AUDIT_SPEND: [
        "fetch_search_terms",
        "fetch_ad_group_performance",
        "fetch_geo_performance",
        "fetch_gsc_query_performance",
        "fetch_ga4_landing_pages",
    ],
    InsightGenerationGoal.CUSTOM: [
        "fetch_ad_group_performance",
    ],
}


def goal_heading_text(goal: InsightGenerationGoal, *, custom_goal: str = "") -> str:
    if goal == InsightGenerationGoal.CUSTOM:
        return (custom_goal or "").strip() or GOAL_LABELS[InsightGenerationGoal.CUSTOM]
    return GOAL_LABELS[goal]


def parse_goal_value(value: object) -> InsightGenerationGoal:
    if isinstance(value, InsightGenerationGoal):
        return value
    s = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not s:
        raise ValueError(
            "goal is required; use one of: "
            + ", ".join(repr(m.value) for m in InsightGenerationGoal)
        )
    try:
        return InsightGenerationGoal(s)
    except ValueError as exc:
        raise ValueError(
            f"Unknown goal {value!r}. Expected one of: "
            + ", ".join(repr(m.value) for m in InsightGenerationGoal)
        ) from exc
