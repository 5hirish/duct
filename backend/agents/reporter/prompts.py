"""Prompt strings and builders for the generate agent and Gemini synthesis.

Structured following Gemini 2.5/3 prompting best practices:
- XML-style tags for clear section demarcation
- Role/constraints in system instruction, data first in user prompt
- Explicit self-critique step before output
- Few-shot example of desired finding quality
- Conciseness constraints (Gemini defaults to verbose)
- Expert PPC analysis frameworks (Vallaeys, ALM Corp, KlientBoost)

References:
  docs/guides/gemini-prompting.md
  https://ai.google.dev/gemini-api/docs/prompting-strategies
"""

from __future__ import annotations

import json
from typing import Any

from agents.reporter.goals import GOAL_DIRECTIVES, ReportGenerationGoal, goal_heading_text

# ---------------------------------------------------------------------------
# Analysis protocol — XML-tagged structure following Gemini best practices.
# Encodes multi-step reasoning (nomadtools barrio/thoughtpolice pattern)
# combined with expert PPC analysis frameworks.
# ---------------------------------------------------------------------------

ANALYSIS_PROTOCOL = """\
<role>
You are a senior paid media analyst producing an operator brief.
You receive a deterministic baseline analysis plus raw and supplementary data.
Your job is to reason through the data, validate or override baseline classifications,
cross-reference data sources, and produce findings backed by specific evidence chains.
</role>

<constraints>
- Verbosity: Low. Be direct and operator-focused. No filler, no hedging.
- Use only data from the payloads; do not invent metrics.
- Each finding must cite specific numbers from the data.
- Prefer concrete operator language over abstract marketing language.
- If evidence is weak, say so with lower confidence — do not inflate.
</constraints>

<analysis_protocol>

Step 1 — READ BASELINE:
Read the deterministic brief classifications. These are your starting point, not gospel.
Note which campaigns are classified as scale, monitor, pause, refresh, refine, or investigate.

Step 2 — EVALUATE PER CAMPAIGN against business context:
For each campaign, check whether the baseline classification makes sense:
- A $200 CPA classified as "pause" may be correct for ecommerce but wrong for enterprise SaaS with $50k ACV
- A 2.0x ROAS classified as "refine" may deserve "scale" if the account is new and still learning
- A "monitor" campaign consuming 40% of budget deserves scrutiny regardless of ROAS
- Check for DIMINISHING RETURNS: is the campaign past the point where marginal CPA exceeds allowable CPA?
  The first $10k of spend may yield $30 CPA; the next $10k may yield $120 CPA. Blended metrics hide this.
- If you disagree with a classification, add a classification_override with your reasoning

Step 3 — CROSS-REFERENCE supplementary data:
Analyze supplementary data against campaign performance. Look for CROSS-DIMENSIONAL patterns:
- Search terms × campaign: which specific queries inflate CPA on underperforming campaigns?
- Device × campaign: is one device segment dragging down an otherwise healthy campaign?
- Device × search term: do high-CPA terms perform differently by device?
- Geo × campaign: geographic concentration issues or untapped expansion opportunities?
- Ad group × campaign: is one ad group dragging the parent campaign classification?
- Look for KEYWORD CANNIBALIZATION: same high-intent terms across multiple campaigns causing self-competition
- Look for NETWORK BLEED: campaigns spending on Search Partners or Display without the advertiser realizing

Step 4 — BUILD EVIDENCE CHAINS for each finding:
Be specific, not generic. Each evidence_chain must name:
- primary_metric: the headline number that triggered the finding
- contributing_factors: specific data points from supplementary data that explain WHY
- data_sources_used: which datasets you drew from

Step 5 — PRODUCE OUTPUT:
Generate findings, overrides, and recommended actions.
Prioritize using ICE scoring (Impact × Confidence × Ease):
- High impact + high confidence + easy to execute = urgent priority
- High impact but low confidence = investigate priority
- Low impact = low priority regardless of confidence
Each recommended action must be concrete enough to execute this week.

</analysis_protocol>

<output_format>

Finding style — each finding must include:
- A short, specific title (not "Performance was mixed")
- 1-3 pieces of evidence citing specific numbers from the data
- An evidence_chain linking supplementary data to the finding
- Why it matters commercially (dollar impact when possible)
- A clear recommended action (scale, pause, monitor, refresh, refine, or investigate)
- A confidence level based on evidence strength

Narrative style:
- verdict: one sentence, operator-ready (what happened and what it means)
- summary: 2-3 sentences covering the key story of the period
- operator_takeaway: the single most important action to take this week

</output_format>

<example_finding>

This is the quality bar for a finding:

Title: "Non-brand mobile CPA is 3x desktop — creative fatigue on small screens"
Evidence:
- "Campaign 'NB | Core Terms' mobile CPA $186 vs desktop CPA $62 (3x gap)"
- "Mobile CTR dropped from 4.2% to 2.8% period-over-period while desktop CTR held at 5.1%"
- "Search term 'compare plans' drives 18% of mobile spend with 0 conversions"
Evidence chain:
  primary_metric: cost_per_conversion
  contributing_factors: ["mobile CTR decline suggests creative fatigue", "search term 'compare plans' non-converting on mobile"]
  data_sources_used: ["device_performance", "search_terms"]
Impact: "$2,800/week wasted on non-converting mobile traffic for this campaign alone"
Recommended action: "Add mobile bid adjustment -40% on NB | Core Terms while refreshing mobile ad copy. Add 'compare plans' as negative keyword."
Confidence: high

This is NOT acceptable:
Title: "Some campaigns need optimization"
Evidence: "Performance was mixed overall"

</example_finding>

<self_critique>
Before producing your final output, verify:
1. Did every finding cite specific numbers, not just directional language?
2. Does each evidence_chain reference at least one supplementary data source?
3. Are recommended_actions specific enough to execute this week?
4. Did I check for cross-dimensional patterns (device × search term, geo × campaign)?
5. Did I flag any classification overrides where the baseline was wrong given business context?
6. Is the narrative verdict operator-ready — would a PPC manager know what to do after reading it?
</self_critique>
"""

# ---------------------------------------------------------------------------
# Per-dataset analysis guides — injected alongside supplementary data so the
# LLM knows exactly what to look for in each data slice.
# Enhanced with expert PPC frameworks (Vallaeys N-gram analysis, ALM Corp
# signal architecture, KlientBoost audit patterns).
# ---------------------------------------------------------------------------

SUPPLEMENTARY_ANALYSIS_GUIDES: dict[str, str] = {
    "search_terms": (
        "ANALYZE search terms by:\n"
        "- Identify terms consuming >5% of campaign spend with 0 conversions — negative keyword candidates\n"
        "- Identify terms with ROAS >2x account average — expansion candidates for exact match\n"
        "- Flag broad match terms bleeding into irrelevant queries\n"
        "- N-GRAM ANALYSIS: break multi-word queries into components to find systematic waste patterns\n"
        "  (e.g., if 'free', 'cheap', 'jobs' appear across many non-converting queries, flag the pattern)\n"
        "- CANNIBALIZATION: flag the same high-intent terms appearing across multiple campaigns\n"
        "- Cross-reference: for each underperforming campaign, which specific search terms inflate its CPA?\n"
        "- Quantify wasted spend on non-converting terms as dollar savings potential"
    ),
    "device_performance": (
        "ANALYZE device splits by:\n"
        "- For each campaign, compare device CPA and conversion rate (mobile vs desktop vs tablet)\n"
        "- Flag campaigns where one device has CPA >2x another — bid adjustment candidates\n"
        "- Check if mobile is dragging down an otherwise healthy campaign's blended metrics\n"
        "- CROSS-DIMENSIONAL: does the high-CPA device also have lower CTR (creative issue) or\n"
        "  lower conversion rate (landing page issue)? These require different fixes.\n"
        "- Identify devices where conversion volume is strong but budget-constrained\n"
        "- Look for DIMINISHING RETURNS by device: is desktop profitable but mobile past the marginal CPA threshold?"
    ),
    "geo_performance": (
        "ANALYZE geographic data by:\n"
        "- Identify regions with spend but 0 conversions — geo exclusion candidates\n"
        "- Identify regions with strong ROAS but low impression share — expansion candidates\n"
        "- Flag regions where CPA is >2x account average\n"
        "- CONCENTRATION RISK: is >60% of spend in one region? If that region softens, the account is exposed.\n"
        "- Cross-reference: do underperforming campaigns have geographic concentration issues?\n"
        "- Quantify spend in non-converting regions as potential savings\n"
        "- Look for GEO × DEVICE patterns: regions where mobile performs differently than desktop"
    ),
    "ad_group_performance": (
        "ANALYZE ad groups by:\n"
        "- Within each campaign, find ad groups consuming >30% of spend with below-average ROAS\n"
        "- Identify ad groups with strong conversion rates that could absorb more budget\n"
        "- Flag ad groups where the parent campaign looks 'mixed' because one ad group drags it down\n"
        "- CANNIBALIZATION: are multiple ad groups bidding on overlapping terms, inflating CPCs?\n"
        "- Cross-reference: would pausing one ad group change the campaign-level classification?\n"
        "- Look for ad groups with declining CTR period-over-period — creative fatigue indicator\n"
        "- MARGINAL RETURNS: within a campaign, which ad groups have the best marginal CPA?"
    ),
}


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _format_business_context(biz_ctx: dict[str, Any] | None) -> str:
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
    return "<business_context>\n" + "\n".join(lines) + "\n</business_context>"


def get_system_prompt(
    *,
    goal: ReportGenerationGoal | None = None,
    custom_goal: str = "",
    context: str = "",
    business_context: dict[str, Any] | None = None,
) -> str:
    """System instruction: analysis protocol + business context + goal directive.

    Follows Gemini best practice: role and constraints first, then context.
    """
    sections: list[str] = [ANALYSIS_PROTOCOL]

    biz_section = _format_business_context(business_context)
    if biz_section:
        sections.append(biz_section)

    if goal is not None:
        heading = goal_heading_text(goal, custom_goal=custom_goal)
        sections.append(f"<user_goal>\n{heading}\n</user_goal>")

    if context:
        sections.append(f"<additional_context>\n{context}\n</additional_context>")

    if goal is not None:
        directive = GOAL_DIRECTIVES.get(goal, "")
        if directive:
            sections.append(directive)

    return "\n\n".join(sections)


def get_synthesis_user_prompt(
    brief_dict: dict[str, Any],
    raw_payload: dict[str, Any],
    *,
    supplementary: dict[str, Any] | None = None,
) -> str:
    """User message with data payloads for synthesis.

    Follows Gemini best practice: all data/context FIRST, task instruction LAST.
    Each supplementary dataset gets specific analysis instructions alongside the data.
    """
    compact_brief = json.dumps(brief_dict, separators=(",", ":"), default=str)[:120_000]
    compact_raw = json.dumps(raw_payload, separators=(",", ":"), default=str)[:120_000]

    # --- Data section (FIRST) ---
    parts = [
        "<data>\n",
        f"<deterministic_brief>\n{compact_brief}\n</deterministic_brief>\n",
        f"<raw_campaign_data>\n{compact_raw}\n</raw_campaign_data>",
    ]

    if supplementary:
        parts.append("\n\n<supplementary_data>")
        for tool_name, data in supplementary.items():
            report_type = data.get("report_type", tool_name)
            row_count = data.get("row_count", "?")

            # Inject per-dataset analysis guide
            guide = SUPPLEMENTARY_ANALYSIS_GUIDES.get(report_type, "")
            if not guide:
                guide = SUPPLEMENTARY_ANALYSIS_GUIDES.get(tool_name.replace("fetch_", ""), "")

            compact = json.dumps(data, separators=(",", ":"), default=str)[:60_000]
            header = f"\n<dataset type=\"{report_type}\" rows=\"{row_count}\">"
            if guide:
                parts.append(f"{header}\n{guide}\n\n{compact}\n</dataset>")
            else:
                parts.append(f"{header}\n{compact}\n</dataset>")
        parts.append("\n</supplementary_data>")

    parts.append("\n</data>")

    # --- Task instruction (LAST, per Gemini long-context best practice) ---
    parts.append(
        "\n\n<task>\n"
        "Based on all the data above, produce your structured analysis.\n"
        "Cross-reference supplementary data with campaign performance.\n"
        "Cite specific numbers in every finding. Follow the analysis protocol.\n"
        "Remember to run the self-critique checklist before finalizing.\n"
        "</task>"
    )

    return "\n".join(parts)
