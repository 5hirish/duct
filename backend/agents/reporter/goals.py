"""Canonical report-generation goals (API + tool routing + prompts)."""

from __future__ import annotations

from enum import StrEnum


class ReportGenerationGoal(StrEnum):
    LOWER_CAC = "lower_cac"
    MAXIMIZE_ROAS = "maximize_roas"
    SCALE_CONVERSIONS = "scale_conversions"
    AUDIT_SPEND = "audit_spend"
    CUSTOM = "custom"


GOAL_LABELS: dict[ReportGenerationGoal, str] = {
    ReportGenerationGoal.LOWER_CAC: "Lower CAC",
    ReportGenerationGoal.MAXIMIZE_ROAS: "Maximize ROAS",
    ReportGenerationGoal.SCALE_CONVERSIONS: "Scale conversions",
    ReportGenerationGoal.AUDIT_SPEND: "Audit spend efficiency",
    ReportGenerationGoal.CUSTOM: "Custom goal",
}

# Analysis directives keyed by goal (system prompt).
GOAL_DIRECTIVES: dict[ReportGenerationGoal, str] = {
    ReportGenerationGoal.LOWER_CAC: """## Goal-Specific Directive: Lower CAC

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
    ReportGenerationGoal.MAXIMIZE_ROAS: """## Goal-Specific Directive: Maximize ROAS

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
    ReportGenerationGoal.SCALE_CONVERSIONS: """## Goal-Specific Directive: Scale Conversions

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
    ReportGenerationGoal.AUDIT_SPEND: """## Goal-Specific Directive: Audit Spend Efficiency

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
    ReportGenerationGoal.CUSTOM: """## Goal-Specific Directive: Custom objective

Address the user's stated objective using only the supplied data.
Prioritize concrete, measurable recommendations aligned with their wording.
""",
}


def goal_heading_text(goal: ReportGenerationGoal, *, custom_goal: str = "") -> str:
    """Human-readable one-line goal for prompts (custom uses ``custom_goal``)."""
    if goal == ReportGenerationGoal.CUSTOM:
        return (custom_goal or "").strip() or GOAL_LABELS[ReportGenerationGoal.CUSTOM]
    return GOAL_LABELS[goal]


def parse_goal_value(value: object) -> ReportGenerationGoal:
    """Coerce request input to ``ReportGenerationGoal`` (strict: known values only)."""
    if isinstance(value, ReportGenerationGoal):
        return value
    s = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not s:
        raise ValueError(
            "goal is required; use one of: "
            + ", ".join(repr(m.value) for m in ReportGenerationGoal)
        )
    try:
        return ReportGenerationGoal(s)
    except ValueError as exc:
        raise ValueError(
            f"Unknown goal {value!r}. Expected one of: "
            + ", ".join(repr(m.value) for m in ReportGenerationGoal)
        ) from exc
