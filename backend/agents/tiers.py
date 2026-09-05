"""Three models the user picks, one job-to-tier assignment Duct owns.

The user configures **Heavy, Standard and Light**. Duct decides which of the
three every internal job deserves. That division is the whole point: the
customer knows their budget and their preferred vendor, and only Duct knows
that the verification subagent is a narrow arithmetic check while the analyst
pass is the deliverable's ceiling. Exposing one dropdown per call site would
make the user learn our internals in order to spend their money correctly.

The ladder is the second half. ``TIER_ORDER`` is descending and
``resolve_tier_model`` walks it, so a job assigned to Heavy runs on Standard
when Heavy's provider has no credential, and on Light when neither does. It
never walks back up.

**Why this may hop providers when ``models.MODEL_FALLBACK`` may not.** That
dict is deliberately same-provider, one-step, and its docstring gives two
reasons: a fallback has to run on the key the caller handed us, and reaching
for Duct's own key "would move a customer's spend onto our account without
asking". The tier ladder answers the second directly — *the user chose these
three models and this order*, so the hop is asked for rather than assumed. The
first is physical and survives untouched: a tier whose provider is not in
``reachable`` is **skipped**, never attempted. The two mechanisms compose —
``MODEL_FALLBACK`` retries within a tier, this walks between them.

Layering follows the rest of the stack: ``models.py`` owns what a model *is*,
``engines.py`` owns which engine *may use* it, and this owns which tier *gets*
it. Nothing here re-implements either; it calls them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agents.engines import (
    ENGINE_DEFAULT_PROVIDER,
    ENGINE_SUPPORTED_PROVIDERS,
    Engine,
    resolve_engine_model,
)
from agents.models import ModelName, Provider, provider_of


class Tier(StrEnum):
    """What kind of model a job gets. Ordered by capability, descending.

    Named Heavy / Standard / Light rather than the obvious Intelligent /
    Balanced / Quick because ``agents/thinking.py`` already ships a
    user-facing four-rung dial labelled Quick, Balanced, Deep, Exhaustive, and
    both controls appear in the same composer. Tier and thinking are
    orthogonal — a Heavy model can run at Quick thinking — and two dials
    sharing words would read as one duplicated dial.
    """

    HEAVY = "heavy"
    STANDARD = "standard"
    LIGHT = "light"


# Descending. The fallback ladder *is* this tuple; there is no other ordering
# of tiers anywhere in the codebase, and nothing may reverse it.
TIER_ORDER: tuple[Tier, ...] = (Tier.HEAVY, Tier.STANDARD, Tier.LIGHT)


class Job(StrEnum):
    """A model-consuming step, named for what it produces rather than where it lives.

    These are internal identities, not a user-facing vocabulary — the settings
    page shows them only inside a "what runs on each tier" disclosure. Adding
    one requires a ``JOB_TIER`` entry, which the test below this module's
    coverage enforces.
    """

    ANALYSIS = "analysis"          # insights: the pass that writes the brief
    AUDIT = "audit"                # SEO audit: category scoring and findings
    VERIFICATION = "verification"  # the subagent that proves a number
    SYNTHESIS = "synthesis"        # v3: structured JSON from prepared briefs
    DRAFTING = "drafting"          # content: plans, captions, slide copy
    CHAT = "chat"                  # follow-up conversation on a finished artifact
    RESEARCH = "research"          # crawled pages, connector briefs
    MEMORY = "memory"              # background consolidation
    RECAP = "recap"                # conversation summaries and titles


# Duct's assignment. Versioned here, shown read-only in the UI, and not
# user-editable — a per-job picker is precisely the design tiers replaced.
#
# The split is by how much judgement the step needs, not by how visible it is:
# RESEARCH reads enormous context and decides almost nothing, so it sits with
# the background work rather than with the analysis it feeds.
JOB_TIER: dict[Job, Tier] = {
    Job.ANALYSIS:     Tier.HEAVY,
    Job.AUDIT:        Tier.HEAVY,
    Job.VERIFICATION: Tier.STANDARD,
    Job.SYNTHESIS:    Tier.STANDARD,
    Job.DRAFTING:     Tier.STANDARD,
    Job.CHAT:         Tier.STANDARD,
    Job.RESEARCH:     Tier.LIGHT,
    Job.MEMORY:       Tier.LIGHT,
    Job.RECAP:        Tier.LIGHT,
}

# Single-provider triples, one per vendor's own three rungs. Keyed by the
# provider whose key the customer actually has, which is the real-world
# starting condition the "fill from one provider" control exists to serve.
#
# OpenRouter is absent on purpose: its catalogue is a curated sample of 500+
# models rather than a vendor's own ladder, so picking three on the user's
# behalf would be inventing one rather than naming one.
PROVIDER_TRIPLES: dict[Provider, dict[Tier, ModelName]] = {
    # Google — the shipped default. A real three-rung ladder: Pro, Flash,
    # Flash-Lite. All three verified against the live ListModels response and
    # a real generateContent call, because a default that names a model id
    # Google does not serve 404s on every fresh install.
    Provider.GOOGLE_GENAI: {
        Tier.HEAVY: ModelName.GEMINI_3_1_PRO_PREVIEW,
        Tier.STANDARD: ModelName.GEMINI_3_8_FLASH,
        Tier.LIGHT: ModelName.GEMINI_3_5_FLASH_LITE,
    },
    Provider.ANTHROPIC: {
        Tier.HEAVY: ModelName.CLAUDE_OPUS,
        Tier.STANDARD: ModelName.CLAUDE_SONNET,
        Tier.LIGHT: ModelName.CLAUDE_HAIKU,
    },
    Provider.OPENAI: {
        Tier.HEAVY: ModelName.GPT_5_6_SOL,
        Tier.STANDARD: ModelName.GPT_5_6_TERRA,
        Tier.LIGHT: ModelName.GPT_5_6_LUNA,
    },
}

# The provider a fresh install runs on. Google, matching
# ``ENGINE_DEFAULT_PROVIDER[Engine.V1]`` — v1 is the default engine and the
# consolidation target, so the default tier map and the default engine agree
# rather than quietly disagreeing.
DEFAULT_PROVIDER: Provider = Provider.GOOGLE_GENAI

# What a fresh install gets, and what "reset to defaults" writes. Derived from
# the triple above so there is one definition of "Google's three rungs".
#
# Single-provider by construction, and that is load-bearing: one key has to
# configure all three tiers or a new customer finds two of three broken on
# arrival.
DEFAULT_TIER_MODELS: dict[Tier, ModelName] = PROVIDER_TRIPLES[DEFAULT_PROVIDER]


# Why a tier was stepped over. Rendered verbatim by the settings page, so the
# preview a user reads and the reason a run logs are the same string.
SKIP_NO_CREDENTIAL = "no_credential"
SKIP_ENGINE = "engine_unsupported"


@dataclass(frozen=True)
class TierResolution:
    """What a job actually got, and everything that was stepped over to get there."""

    model: ModelName | str
    provider: Provider
    requested: Tier
    # None when no tier could serve and the engine's own default was used.
    tier: Tier | None = None
    # (tier, reason) in the order they were skipped. Empty on the happy path.
    skipped: tuple[tuple[Tier, str], ...] = ()
    # True when this came from the engine floor rather than from the user's map.
    engine_default: bool = False

    @property
    def degraded(self) -> bool:
        """True when the job did not run on the tier it was assigned."""
        return self.tier is not self.requested


def tier_chain(start: Tier) -> tuple[Tier, ...]:
    """``start`` and every tier below it, in descending order.

    Never includes a tier above ``start``: an upgrade is a cost surprise the
    user did not ask for. Mirrors ``execution/policy.effective_autonomy``,
    where a model may only ever lower the posture, never raise it.
    """
    index = TIER_ORDER.index(start)
    return TIER_ORDER[index:]


def resolve_tier_model(
    job: Job,
    engine: Engine,
    *,
    tier_map: dict[str, str] | None = None,
    reachable: frozenset[Provider] = frozenset(),
    override_tier: Tier | None = None,
) -> TierResolution | None:
    """The model for ``job``, walking down from its tier until one can run.

    ``tier_map`` is the user's three picks, keyed by tier value; absent or
    partial is fine, and a missing tier falls back to ``DEFAULT_TIER_MODELS``.
    ``reachable`` is the set of providers this *request* has a credential for —
    passed in rather than read from config because credentials are per-request
    and a module that reaches for globals races across concurrent callers
    carrying different bring-your-own keys (the rule
    ``models.get_api_key_kwargs`` already states).

    ``override_tier`` is the composer's per-run lift: it moves the starting
    rung, so a run "at Heavy" still descends normally if Heavy cannot run.

    Returns ``None`` when no tier is reachable at all. Callers should treat
    that the way ``insights/setup.resolve_model`` already does — fail at the
    door rather than halfway through a brief.
    """
    start = override_tier or JOB_TIER.get(job, Tier.STANDARD)
    supported = ENGINE_SUPPORTED_PROVIDERS.get(engine, frozenset())
    picks = tier_map or {}
    skipped: list[tuple[Tier, str]] = []

    for tier in tier_chain(start):
        raw = str(picks.get(tier.value) or "").strip()
        # An unusable pick degrades to the tier's default rather than skipping
        # the tier — the user asked for this rung, only the model was wrong.
        candidate = raw or DEFAULT_TIER_MODELS[tier].value
        provider = provider_of(candidate)
        if provider is None:
            provider = provider_of(DEFAULT_TIER_MODELS[tier].value) or Provider.ANTHROPIC
            candidate = DEFAULT_TIER_MODELS[tier].value

        if provider not in supported:
            skipped.append((tier, SKIP_ENGINE))
            continue
        if provider not in reachable:
            skipped.append((tier, SKIP_NO_CREDENTIAL))
            continue

        # engines.py has the final word on whether this engine may serve this
        # model — it is where CLI-only ids and OpenRouter passthrough live.
        model = resolve_engine_model(engine, provider, candidate)
        return TierResolution(
            model=model,
            tier=tier,
            provider=provider,
            requested=start,
            skipped=tuple(skipped),
        )

    # No tier could serve. Fall to the engine's own default — today's
    # behaviour, and the floor the whole design stands on.
    #
    # This exists because the default triple is Google and v3's harness is
    # Anthropic-only: Content Studio would otherwise have no model at all on a
    # stock install, which is a worse answer than the one v3 already has. The
    # floor never invents a provider — it uses the engine's declared default,
    # and only when that is actually reachable.
    floor_provider = ENGINE_DEFAULT_PROVIDER[engine]
    if floor_provider in reachable:
        return TierResolution(
            model=resolve_engine_model(engine, floor_provider),
            tier=None,
            provider=floor_provider,
            requested=start,
            skipped=tuple(skipped),
            engine_default=True,
        )

    # Nothing at all. Fail at the door rather than halfway through a brief.
    return None


def describe_skip(tier: Tier, reason: str) -> str:
    """One sentence for a skipped tier, for logs and for the settings page."""
    if reason == SKIP_NO_CREDENTIAL:
        return f"{tier.value} has no API key for its provider"
    if reason == SKIP_ENGINE:
        return f"{tier.value}'s provider is not supported by this engine"
    return f"{tier.value} was unavailable"
