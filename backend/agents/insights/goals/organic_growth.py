"""Organic Growth insight goals — enum, labels, directives, and tool priorities."""

from __future__ import annotations

from enum import StrEnum


class OrganicGrowthGoal(StrEnum):
    DIAGNOSE_TRAFFIC_DROP = "diagnose_traffic_drop"
    GROW_ORGANIC_TRAFFIC = "grow_organic_traffic"
    IMPROVE_RANKINGS = "improve_rankings"
    CONTENT_GAP_ANALYSIS = "content_gap_analysis"
    CUSTOM = "custom"


GOAL_LABELS: dict[OrganicGrowthGoal, str] = {
    OrganicGrowthGoal.DIAGNOSE_TRAFFIC_DROP: "Diagnose traffic drops",
    OrganicGrowthGoal.GROW_ORGANIC_TRAFFIC: "Grow organic traffic",
    OrganicGrowthGoal.IMPROVE_RANKINGS: "Improve rankings",
    OrganicGrowthGoal.CONTENT_GAP_ANALYSIS: "Content gap analysis",
    OrganicGrowthGoal.CUSTOM: "Custom goal",
}

GOAL_DESCRIPTIONS: dict[OrganicGrowthGoal, str] = {
    OrganicGrowthGoal.DIAGNOSE_TRAFFIC_DROP: "Find which queries, pages, or channels lost clicks and impressions.",
    OrganicGrowthGoal.GROW_ORGANIC_TRAFFIC: "Identify top ranking opportunities and pages with untapped potential.",
    OrganicGrowthGoal.IMPROVE_RANKINGS: "Surface pages stuck on page 2–3 and actionable fixes to move them up.",
    OrganicGrowthGoal.CONTENT_GAP_ANALYSIS: "Find topics your competitors rank for that you're missing entirely.",
    OrganicGrowthGoal.CUSTOM: "Describe your own SEO objective.",
}

GOAL_ICONS: dict[OrganicGrowthGoal, str] = {
    OrganicGrowthGoal.DIAGNOSE_TRAFFIC_DROP: "🔍",
    OrganicGrowthGoal.GROW_ORGANIC_TRAFFIC: "📈",
    OrganicGrowthGoal.IMPROVE_RANKINGS: "🏆",
    OrganicGrowthGoal.CONTENT_GAP_ANALYSIS: "✍️",
    OrganicGrowthGoal.CUSTOM: "✏️",
}

# Analysis directives keyed by goal — injected into system prompt.
GOAL_DIRECTIVES: dict[OrganicGrowthGoal, str] = {
    OrganicGrowthGoal.DIAGNOSE_TRAFFIC_DROP: """\
<goal_directive>
## Directive: Diagnose Traffic Drop

Your primary task is root-cause diagnosis. Do not jump to recommendations before establishing causation.

Diagnostic sequence:
1. SCOPE: Was the drop in impressions, clicks, or both?
   - Impressions drop = lost rankings or SERP feature displacement
   - Clicks drop with stable impressions = CTR collapse (SERP layout change or intent mismatch)
   - Both dropping together = broad ranking loss or indexation problem

2. CONCENTRATION: Is the drop broad (dozens of queries/pages) or concentrated (1-3 pages/queries)?
   - Concentrated drop = page-specific issue (content change, technical regression, penalty signal)
   - Broad drop = algorithm update sensitivity, often correlated with E-E-A-T signals or content quality

3. QUERY CLASSIFICATION: For dropping queries, are they:
   - Branded: brand awareness or PR issue, not SEO
   - Non-branded informational: content quality or freshness
   - Non-branded transactional: competitive displacement or intent mismatch

4. TIMELINE: When exactly did the drop start? Cross-reference with:
   - Google algorithm update dates (if known from context)
   - Any site changes noted in period_changes business context
   - Seasonal baselines for the industry

5. TECHNICAL SIGNALS: Flag if any pages with large drops also show:
   - Very low or zero GA4 engagement (possible indexation or redirect issue)
   - Sudden CTR drop with stable impressions (rich result removed, SERP change)

Output: produce a diagnostic verdict first ("The drop is concentrated in 3 non-branded informational
pages, consistent with content freshness sensitivity"), then findings with evidence, then recovery
actions ranked by speed-of-impact.
</goal_directive>
""",

    OrganicGrowthGoal.GROW_ORGANIC_TRAFFIC: """\
<goal_directive>
## Directive: Grow Organic Traffic

Focus on the highest-leverage traffic growth opportunities in the current data.

Growth opportunity hierarchy (analyze in this order):
1. QUICK WINS — existing pages at positions 4-10 with >500 monthly impressions
   These are closest to the first page and need the least lift for meaningful traffic gains.
   Calculate: impressions × (CTR at target position − current CTR) = projected monthly clicks gained
   Use standard CTR curve: pos 1 ~28%, pos 2 ~15%, pos 3 ~11%, pos 4 ~8%, pos 5-10 ~3-7%
   Prioritize the top 5 by projected gains.

2. PAGE 2 RESCUE — pages at positions 11-20
   Position 11-20 pages get almost no clicks (~1-2% CTR) but may have significant impressions.
   Moving one from position 15 to position 8 can be 3-4x the traffic.
   Focus on pages with strong GA4 engagement (content is good, ranking is the problem).

3. CONTENT EXPANSION — queries with high impressions but no strong ranking page
   If the site ranks at position 25+ for a query with 5,000 impressions/month, the existing content
   is weak for that intent. Flag as a content build or heavy revision opportunity.

4. INTERNAL LINK AMPLIFICATION — pages stuck at position 8-15 with strong content
   (high GA4 engagement) but lacking link support are often faster wins than content rewrites.

5. TREND AMPLIFICATION — queries that gained position period-over-period
   Find what's already working and identify why — then apply to related pages.

For each opportunity: estimate monthly traffic gain, recommended action, and effort level (low/medium/high).
</goal_directive>
""",

    OrganicGrowthGoal.IMPROVE_RANKINGS: """\
<goal_directive>
## Directive: Improve Rankings

Focus specifically on the mechanisms causing pages to rank where they do, and what would move them.

Ranking analysis framework:
1. OPPORTUNITY ZONE AUDIT — for every page at positions 4-15 with >200 impressions/month:
   - Current position, impressions, CTR
   - GA4 engagement rate + avg session duration (proxy for content quality signal)
   - Estimated position needed to 2x clicks (use CTR curve)

2. RANKING FACTOR SIGNALS — for underperforming pages, diagnose the likely limiting factor:
   - CONTENT DEPTH: high impressions, low engagement, position 8-15 = content doesn't fully
     answer the query. Fix: expand with specific subtopics the query cluster implies.
   - INTENT MISMATCH: position 6-12 with below-expected CTR for that position.
     The title/meta description doesn't match what searchers expect.
     Fix: rewrite title tag to match dominant query intent.
   - AUTHORITY GAP: pages with strong content (high engagement) stuck at position 8-12.
     Likely need internal links from higher-authority pages.
     Fix: identify 3-5 topically related pages with stronger rankings and add internal links.
   - CANNIBALIZATION: two pages at position 8-14 for the same query cluster.
     Split signal holds both back. Consolidate or implement canonical signals.

3. SERP FEATURE DISPLACEMENT: pages at position 1-3 but below-expected CTR.
   A featured snippet or local pack may be pushing organic results below the fold.
   Note this as context — the fix is schema markup or content restructuring to win the feature.

For each finding: name the specific page, specific queries, and specific fix type.
</goal_directive>
""",

    OrganicGrowthGoal.CONTENT_GAP_ANALYSIS: """\
<goal_directive>
## Directive: Content Gap Analysis

Identify topics the site is missing or under-serving based on query data signals.

Gap detection methodology:
1. IMPRESSION-WITHOUT-RANKING GAPS — queries where the site gets impressions but ranks 20+.
   These are "partial signal" queries: Google knows the site might be relevant but no page
   is authoritative enough. Flag clusters of related queries pointing to the same gap.

2. LOW-COVERAGE QUERY CLUSTERS — groups of related queries where the highest-ranking page
   is at position 15-25. The site has tangential coverage but no dedicated, comprehensive page.
   Action: build or consolidate into a definitive piece on that topic.

3. THIN vs. DEEP CONTENT SIGNAL — pages ranking position 8-15 for queries that imply deep content
   (how-to guides, comparison queries, "best X" queries) but show low GA4 session duration are
   likely thin content ranking on domain authority alone. Vulnerable to displacement.

4. TOFU/MOFU/BOFU COVERAGE MAP:
   - TOFU: informational queries ("how does X work", "what is X") — brand-building, high volume
   - MOFU: evaluation queries ("X vs Y", "best X for Y") — consideration, high commercial value
   - BOFU: transactional queries ("buy X", "X pricing", "X demo") — conversion-intent, must rank
   Identify which funnel stage has the weakest coverage relative to impressions.

5. COMPETITOR DISPLACEMENT SIGNALS: queries where the site recently lost position. This signals
   where a content investment would directly displace a specific ranking result.

Output: a prioritized content roadmap with topic, evidence of demand (impressions/queries),
content format recommendation (hub page, deep guide, comparison post), and estimated traffic opportunity.
</goal_directive>
""",

    OrganicGrowthGoal.CUSTOM: """\
<goal_directive>
## Directive: Custom SEO Objective

Address the user's stated objective using only the supplied organic data (GSC + GA4).
Frame findings in terms of organic search signals: rankings, impressions, CTR, engagement.
Prioritize concrete, page-specific or query-specific recommendations over general advice.
</goal_directive>
""",
}

# Tool names to mark [PRIORITY] in the Phase 1 prompt per goal.
GOAL_TOOL_PRIORITIES: dict[OrganicGrowthGoal, list[str]] = {
    OrganicGrowthGoal.DIAGNOSE_TRAFFIC_DROP: [
        "fetch_gsc_query_performance",
        "fetch_gsc_page_performance",
        "fetch_ga4_landing_pages",
    ],
    OrganicGrowthGoal.GROW_ORGANIC_TRAFFIC: [
        "fetch_gsc_query_performance",
        "fetch_gsc_page_performance",
        "fetch_ga4_landing_pages",
    ],
    OrganicGrowthGoal.IMPROVE_RANKINGS: [
        "fetch_gsc_query_performance",
        "fetch_gsc_page_performance",
        "fetch_ga4_landing_pages",
    ],
    OrganicGrowthGoal.CONTENT_GAP_ANALYSIS: [
        "fetch_gsc_query_performance",
        "fetch_gsc_page_performance",
    ],
    OrganicGrowthGoal.CUSTOM: [
        "fetch_gsc_query_performance",
        "fetch_gsc_page_performance",
    ],
}


def goal_heading_text(goal: OrganicGrowthGoal, *, custom_goal: str = "") -> str:
    if goal == OrganicGrowthGoal.CUSTOM:
        return (custom_goal or "").strip() or GOAL_LABELS[OrganicGrowthGoal.CUSTOM]
    return GOAL_LABELS[goal]


def parse_goal_value(value: object) -> OrganicGrowthGoal:
    if isinstance(value, OrganicGrowthGoal):
        return value
    s = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not s:
        raise ValueError(
            "goal is required; use one of: "
            + ", ".join(repr(m.value) for m in OrganicGrowthGoal)
        )
    try:
        return OrganicGrowthGoal(s)
    except ValueError as exc:
        raise ValueError(
            f"Unknown organic goal {value!r}. Expected one of: "
            + ", ".join(repr(m.value) for m in OrganicGrowthGoal)
        ) from exc
