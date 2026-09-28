"""Insights cases, on Solo's synthetic accounts (``solo_world.py``)."""

from __future__ import annotations

from agents.core.context import format_business_context
from tests.eval.cases.solo_world import SoloWorld
from tests.eval.gate import Case, QuotedTotal
from tests.eval.rubric import Marker

# Rendered by the production formatter, so the case reads the block a real
# project's turn carries.
SOLO_CONTEXT = format_business_context({
    "business_name": "Solo",
    "business_description": "Budgeting for freelancers; iOS, Android and web (solobudget.app)",
    "industry": "Personal finance software",
    "business_model": "Subscription, €7.99 a month after a 14-day trial",
    "audience_segment": "Freelancers in Spain, Germany and France",
    "business_goals": "900 sign-ups a week; organic search is the cheapest channel",
    "target_cpa": 12,
    "primary_organic_kpi": "Organic sessions to the blog",
})

ORGANIC = Case(
    id="insights/solo-organic-slip",
    agent="insights",
    question=(
        "How did organic search do over the last four weeks compared with the four "
        "weeks before, and what should we do about it?"
    ),
    business_context=SOLO_CONTEXT,
    world=SoloWorld,
    must_fetch=("ga4_landing_pages", "gsc_page_performance"),
    must_quote=(
        QuotedTotal(
            "ga4_landing_pages",
            ("subtotals.channel.Organic Search.sessions", "totals.sessions"),
            "the organic (or all-channel) session total",
        ),
    ),
    markers=(
        Marker(
            "names_the_slip",
            "Names the freelance tax guide (/blog/freelance-tax-guide) as the page whose "
            "organic traffic fell the most.",
        ),
        Marker(
            "explains_with_ranking",
            "Ties that fall to the page's Search Console ranking (average position) getting "
            "worse, not to demand or seasonality alone.",
        ),
    ),
    cost_cap_usd=0.60,
    max_model_calls=40,
)

INSIGHTS_CASES = (ORGANIC,)
