"""The integrity check library — prove the number before you use it.

Why this exists, in one statistic from the engagement it is modelled on: of 93
turns across a month, **60% were establishing whether a number could be trusted
at all; 16% were optimisation.** Every serious defect found in that month
presented as healthy — an experiment "running" with nobody bucketed for 74
days, a tag that "fires" but fails at runtime, 23 of 36 "upgrades" coming from
seven QA accounts in one country. No system in the stack alerted on any of it,
because a dashboard renders a corrupt number in the same font as a correct one.

Design, and the one rule that matters
-------------------------------------
**A check declares the catalog entities it needs and is SKIPPED, visibly, when
they are absent.** No check names a connector in its logic. That is what makes
the library connector-agnostic: adding a connector is a catalog entry (see
``agents/insights/fetchers.py``), and every check whose requirements it
completes starts running on its own — nothing here changes.

The skipped list is not an implementation detail to hide. It is half the
output: "I could not check whether your conversions include internal traffic,
because GA4 is not connected" is a useful sentence, and it is the sentence a
dashboard can never say. ``coverage`` renders both halves.

Checks are *questions*, not assertions. They are handed to a verifier subagent
that fetches the entities and judges; encoding thresholds here would fossilise
account-specific numbers into shared code.
"""

from __future__ import annotations

from dataclasses import dataclass

# Families, in the order the retrospective found them to matter.
CONTAMINATION = "contamination"  # is this real traffic?
LIVENESS = "liveness"            # is it still on?
UNITS = "units"                  # is this number comparable?
MONEY = "money"                  # did it actually settle?
FUNNEL = "funnel"                # where is the ask?

FAMILY_LABELS = {
    CONTAMINATION: "Contamination",
    LIVENESS: "Liveness",
    UNITS: "Units & semantics",
    MONEY: "Money truth",
    FUNNEL: "Funnel gap",
}


@dataclass(frozen=True)
class Check:
    """One integrity question, and what it needs to be answerable."""

    id: str
    family: str
    title: str
    # Catalog entity ids. ALL must be available or the check is skipped.
    requires: tuple[str, ...]
    # What the verifier must establish, phrased as an instruction to a analyst.
    question: str
    # Said to the user when the check cannot run — what they would learn by
    # connecting the missing source. Never a nag; a statement of the gap.
    if_skipped: str


CHECKS: tuple[Check, ...] = (
    Check(
        id="spend_without_conversions",
        family=LIVENESS,
        title="Conversion tracking alive",
        requires=("campaign_performance",),
        question=(
            "Is there meaningful spend with zero or near-zero recorded conversions across "
            "the whole account, or a campaign that stopped recording conversions while "
            "still spending? Both usually mean broken tracking rather than bad performance, "
            "and the difference changes the recommendation completely."
        ),
        if_skipped="Whether conversion tracking is actually recording could not be checked.",
    ),
    Check(
        id="volume_step_change",
        family=LIVENESS,
        title="Step changes in volume",
        requires=("campaign_performance",),
        question=(
            "Compare each campaign against its previous period. Is any metric down by an "
            "amount that looks like something switched off rather than performance drifting "
            "— a collapse to zero, or a fall of most of the volume in one step? Say which, "
            "and say you cannot tell a pause from a tracking break without more evidence."
        ),
        if_skipped="Sudden collapses in volume could not be distinguished from gradual decline.",
    ),
    Check(
        id="shared_account_tenancy",
        family=CONTAMINATION,
        title="Account shared with other products",
        requires=("campaign_performance",),
        question=(
            "Do the campaign names suggest more than one product or brand in this account? "
            "Ad accounts are routinely shared, and a total that mixes two products is wrong "
            "in a way no per-campaign number reveals. Name the groups you see; do not guess "
            "which one the user meant."
        ),
        if_skipped="Whether this account mixes several products could not be checked.",
    ),
    Check(
        id="geo_concentration",
        family=CONTAMINATION,
        title="Conversions concentrated in one place",
        requires=("geo_performance",),
        question=(
            "Are conversions concentrated in a location that does not match the business's "
            "market? Internal and QA traffic clusters geographically, and it lands "
            "disproportionately in the low-volume segments decisions get made on."
        ),
        if_skipped="Internal or QA traffic clustering by location could not be checked.",
    ),
    Check(
        id="internal_traffic",
        family=CONTAMINATION,
        title="Internal traffic in the analytics",
        requires=("ga4_landing_pages",),
        question=(
            "Is there traffic to internal, staging or admin paths, or engagement patterns "
            "that look like the team rather than customers? Analytics tools do not filter "
            "internal traffic by default, so every funnel is wrong until someone checks."
        ),
        if_skipped="Internal traffic in the analytics could not be checked.",
    ),
    Check(
        id="attribution_window_mismatch",
        family=UNITS,
        title="Numbers from different attribution models",
        requires=("campaign_performance", "ga4_conversion_paths"),
        question=(
            "Do the ad platform's conversions and the analytics platform's differ by more "
            "than rounding? They use different attribution models and windows, so they are "
            "not the same quantity. If you cite both, say which is which — never present "
            "the gap as a discrepancy to be fixed."
        ),
        if_skipped="Ad-platform and analytics conversion counts could not be compared.",
    ),
    Check(
        id="conversion_double_count",
        family=UNITS,
        title="One conversion counted more than once",
        requires=("campaign_performance",),
        question=(
            "Does the conversion total look inflated relative to clicks — a rate that is "
            "implausible for this business? One action imported under several conversion "
            "names multiplies the count and the ROAS with it."
        ),
        if_skipped="Double-counted conversions could not be checked.",
    ),
    Check(
        id="organic_ctr_gap",
        family=FUNNEL,
        title="Ranking without clicks",
        requires=("gsc_query_performance",),
        question=(
            "Are there queries ranking well with impressions but very few clicks? That is a "
            "title/snippet problem, not a ranking problem, and it is the cheapest fix in "
            "organic search."
        ),
        if_skipped="Queries that rank but do not earn clicks could not be checked.",
    ),
    Check(
        id="monetisation_moment",
        family=FUNNEL,
        title="Value delivered without an ask",
        requires=("ga4_landing_pages", "campaign_performance"),
        question=(
            "Are paid visitors reaching pages that deliver the product's value without "
            "encountering a paywall, signup or upgrade prompt? An ad platform is "
            "structurally incapable of seeing this — it sees a click in and a pixel out — "
            "and it is where the money usually is."
        ),
        if_skipped="Whether paid traffic is asked to pay could not be checked.",
    ),
    # --- Money truth. No revenue connector exists yet, so these are skipped
    #     today. They are declared anyway, deliberately: they are the strongest
    #     checks in the library, the skip tells the user exactly what a billing
    #     connection would buy, and the day one lands they run with no code
    #     change here. This is the connector-agnostic contract, demonstrated.
    Check(
        id="settled_revenue_reconciliation",
        family=MONEY,
        title="Reported conversions vs settled revenue",
        requires=("billing_charges",),
        question=(
            "Do the conversions the ad platforms report reconcile to charges that actually "
            "settled? Ad platforms report their own homework; only the biller knows."
        ),
        if_skipped=(
            "Reported conversions could not be reconciled against money that actually "
            "settled — no billing source is connected."
        ),
    ),
    Check(
        id="involuntary_churn",
        family=MONEY,
        title="Revenue lost to failed payments",
        requires=("billing_charges",),
        question=(
            "How much recurring revenue is being lost to failed renewals, and how does that "
            "compare with new revenue won? A company can optimise acquisition while losing "
            "more out the back than it wins at the front."
        ),
        if_skipped=(
            "Revenue lost to failed payments could not be measured — no billing source is "
            "connected."
        ),
    ),
    Check(
        id="acquisition_vs_expansion",
        family=MONEY,
        title="New customers vs expansion",
        requires=("billing_subscriptions",),
        question=(
            "Are upgrades from existing customers being counted as new acquisitions? The "
            "distinction routinely swings acquisition counts by two to three times, and it "
            "is invisible in every ad platform."
        ),
        if_skipped=(
            "New customers could not be separated from upgrades — no billing source is "
            "connected."
        ),
    ),
)


@dataclass(frozen=True)
class Coverage:
    """Which checks this project's connections can actually answer."""

    runnable: tuple[Check, ...]
    skipped: tuple[Check, ...]

    @property
    def gaps(self) -> list[str]:
        """The "what I could not verify" lines, for the artifact."""
        return [c.if_skipped for c in self.skipped]


def coverage(available_entities: set[str] | list[str]) -> Coverage:
    """Split the library against the entities this project can fetch.

    The only input is a set of catalog entity ids — no connector names — which
    is what keeps the library connector-agnostic.
    """
    have = set(available_entities)
    runnable = tuple(c for c in CHECKS if set(c.requires) <= have)
    skipped = tuple(c for c in CHECKS if not set(c.requires) <= have)
    return Coverage(runnable=runnable, skipped=skipped)


def all_checks_block() -> str:
    """The whole library, rendered for a system prompt.

    Static on purpose — identical for every customer, so it sits safely in the
    cached prefix. Coverage is NOT baked in: the verifier discovers what it can
    reach by fetching, and a ``not_connected`` result turns that check into its
    own ``if_skipped`` line. Rendering per-project coverage here would give
    every customer a distinct prefix to buy information the tool returns anyway.
    """
    lines: list[str] = []
    for family in (LIVENESS, CONTAMINATION, UNITS, FUNNEL, MONEY):
        members = [c for c in CHECKS if c.family == family]
        if not members:
            continue
        lines.append(f"\n### {FAMILY_LABELS[family]}")
        for check in members:
            lines.append(f"\n**{check.title}** — needs: {', '.join(check.requires)}")
            lines.append(f"  {check.question}")
            lines.append(f"  If unreachable, report exactly: \"{check.if_skipped}\"")
    return "\n".join(lines)
