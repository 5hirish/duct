"""The tier ladder: what it picks, what it skips, and what it must never do.

The invariants worth a test are the ones a future edit could plausibly break
without anything else failing: the ladder only descends, an unreachable tier is
stepped over rather than attempted, and every Job has a tier.
"""

from __future__ import annotations

import pytest

from agents.engines import Engine
from agents.models import Modality, ModelName, Provider, model_emits, provider_of
from agents.tiers import (
    DEFAULT_PROVIDER,
    DEFAULT_TIER_MODELS,
    JOB_TIER,
    PROVIDER_TRIPLES,
    SKIP_ENGINE,
    SKIP_NO_CREDENTIAL,
    TIER_ORDER,
    Job,
    Tier,
    resolve_tier_model,
    tier_chain,
)

ALL_PROVIDERS = frozenset(Provider)
ANTHROPIC_ONLY = frozenset({Provider.ANTHROPIC})
GOOGLE_ONLY = frozenset({Provider.GOOGLE_GENAI})

ANTHROPIC_MAP = {
    "heavy": ModelName.CLAUDE_OPUS.value,
    "standard": ModelName.CLAUDE_SONNET.value,
    "light": ModelName.CLAUDE_HAIKU.value,
}


# ---------------------------------------------------------------------------
# provider_of — the credential decision every other rule depends on
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "model,expected",
    [
        (ModelName.CLAUDE_OPUS, Provider.ANTHROPIC),
        (ModelName.GEMINI_3_8_FLASH, Provider.GOOGLE_GENAI),
        (ModelName.GPT_5_6_SOL, Provider.OPENAI),
        ("deepseek/deepseek-v4-flash", Provider.OPENROUTER),
        # The one that would spend the wrong key if the prefix test ran first:
        # a vendor-prefixed slug bills through OpenRouter, not through Anthropic.
        ("anthropic/claude-opus-5", Provider.OPENROUTER),
    ],
)
def test_provider_of_reads_the_id_shape(model, expected):
    assert provider_of(model) is expected


def test_provider_of_refuses_to_guess():
    """None is an answer. A caller choosing a credential must not get a guess."""
    assert provider_of("made-up-model") is None
    assert provider_of("") is None


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------

def test_tier_chain_never_ascends():
    assert tier_chain(Tier.HEAVY) == (Tier.HEAVY, Tier.STANDARD, Tier.LIGHT)
    assert tier_chain(Tier.STANDARD) == (Tier.STANDARD, Tier.LIGHT)
    assert tier_chain(Tier.LIGHT) == (Tier.LIGHT,)


def test_every_job_has_a_tier():
    """A new Job without an assignment would silently resolve to STANDARD."""
    assert set(JOB_TIER) == set(Job)


def test_happy_path_uses_the_assigned_tier():
    got = resolve_tier_model(Job.ANALYSIS, Engine.V1, tier_map=ANTHROPIC_MAP, reachable=ALL_PROVIDERS)
    assert got.model is ModelName.CLAUDE_OPUS
    assert got.tier is Tier.HEAVY
    assert got.skipped == ()
    assert not got.degraded


def test_unreachable_tier_is_skipped_not_attempted():
    """The credential half of MODEL_FALLBACK's rule survives the tier ladder."""
    mixed = {**ANTHROPIC_MAP, "heavy": ModelName.GPT_5_6_SOL.value}
    got = resolve_tier_model(Job.ANALYSIS, Engine.V1, tier_map=mixed, reachable=ANTHROPIC_ONLY)
    assert got.tier is Tier.STANDARD
    assert got.model is ModelName.CLAUDE_SONNET
    assert got.degraded
    assert got.skipped == ((Tier.HEAVY, SKIP_NO_CREDENTIAL),)


def test_ladder_descends_more_than_one_rung():
    two_missing = {
        "heavy": ModelName.GPT_5_6_SOL.value,
        "standard": ModelName.GEMINI_3_8_FLASH.value,
        "light": ModelName.CLAUDE_HAIKU.value,
    }
    got = resolve_tier_model(Job.ANALYSIS, Engine.V1, tier_map=two_missing, reachable=ANTHROPIC_ONLY)
    assert got.tier is Tier.LIGHT
    assert [tier for tier, _ in got.skipped] == [Tier.HEAVY, Tier.STANDARD]


def test_engine_support_skips_a_tier_even_with_a_key():
    """v3 is Anthropic-only, so a reachable Google model still cannot serve it."""
    google = {t: ModelName.GEMINI_3_8_FLASH.value for t in ("heavy", "standard", "light")}
    got = resolve_tier_model(Job.DRAFTING, Engine.V3, tier_map=google, reachable=ALL_PROVIDERS)
    # Every tier the job could use was refused for the engine, not the key...
    assert {reason for _, reason in got.skipped} == {SKIP_ENGINE}
    # ...and the engine's own default is what caught the fall.
    assert got.engine_default and got.provider is Provider.ANTHROPIC


def test_v3_skips_the_unsupported_tier_and_keeps_going():
    mixed = {**ANTHROPIC_MAP, "standard": ModelName.GPT_5_6_TERRA.value}
    got = resolve_tier_model(Job.DRAFTING, Engine.V3, tier_map=mixed, reachable=ALL_PROVIDERS)
    assert got.tier is Tier.LIGHT
    assert got.skipped == ((Tier.STANDARD, SKIP_ENGINE),)


def test_nothing_reachable_at_all_returns_none():
    """Fail at the door, the way insights/setup.resolve_model already does."""
    assert resolve_tier_model(Job.ANALYSIS, Engine.V1, tier_map=ANTHROPIC_MAP, reachable=frozenset()) is None


def test_unknown_model_degrades_to_the_tier_default_not_a_skip():
    """The user asked for this rung; only the model string was wrong."""
    junk = {**ANTHROPIC_MAP, "heavy": "not-a-real-model"}
    got = resolve_tier_model(Job.ANALYSIS, Engine.V1, tier_map=junk, reachable=ALL_PROVIDERS)
    assert got.tier is Tier.HEAVY
    assert got.model is DEFAULT_TIER_MODELS[Tier.HEAVY]
    assert not got.engine_default


def test_empty_map_is_todays_behaviour():
    """An unset map must resolve, so the migration is a no-op."""
    got = resolve_tier_model(Job.ANALYSIS, Engine.V1, tier_map={}, reachable=ALL_PROVIDERS)
    assert got.model is DEFAULT_TIER_MODELS[Tier.HEAVY]


def test_override_tier_lifts_the_starting_rung():
    got = resolve_tier_model(
        Job.RECAP, Engine.V1, tier_map=ANTHROPIC_MAP, reachable=ALL_PROVIDERS, override_tier=Tier.HEAVY
    )
    assert got.tier is Tier.HEAVY
    assert got.requested is Tier.HEAVY


def test_override_still_descends_when_it_cannot_run():
    mixed = {**ANTHROPIC_MAP, "heavy": ModelName.GPT_5_6_SOL.value}
    got = resolve_tier_model(
        Job.RECAP, Engine.V1, tier_map=mixed, reachable=ANTHROPIC_ONLY, override_tier=Tier.HEAVY
    )
    assert got.tier is Tier.STANDARD


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_default_triple_is_single_provider():
    """One key must configure all three tiers, or a new install arrives broken."""
    providers = {provider_of(model) for model in DEFAULT_TIER_MODELS.values()}
    assert providers == {DEFAULT_PROVIDER}


def test_default_provider_is_google_and_matches_the_default_engine():
    """The shipped tier map and the shipped engine must agree on a provider."""
    from agents.engines import ENGINE_DEFAULT_PROVIDER

    assert DEFAULT_PROVIDER is Provider.GOOGLE_GENAI
    assert ENGINE_DEFAULT_PROVIDER[Engine.V1] is DEFAULT_PROVIDER


def test_default_triple_is_three_distinct_rungs():
    """Heavy that equals Standard is not a ladder, it is one model typed twice."""
    assert len(set(DEFAULT_TIER_MODELS.values())) == 3


def test_every_provider_triple_is_single_provider_and_complete():
    for provider, triple in PROVIDER_TRIPLES.items():
        assert set(triple) == set(TIER_ORDER), f"{provider} is missing a tier"
        assert {provider_of(m) for m in triple.values()} == {provider}


def test_google_defaults_run_natively_on_the_default_engine():
    """A stock install with only a Google key resolves every tier natively."""
    for job, expected in (
        (Job.ANALYSIS, Tier.HEAVY),
        (Job.DRAFTING, Tier.STANDARD),
        (Job.MEMORY, Tier.LIGHT),
    ):
        got = resolve_tier_model(job, Engine.V1, reachable=GOOGLE_ONLY)
        assert got is not None and got.tier is expected
        assert not got.degraded and not got.engine_default


def test_v3_falls_to_the_engine_default_rather_than_stranding():
    """Content Studio is v3-only and v3 is Anthropic-only.

    With a Google default triple no tier can serve it, so the ladder's floor —
    the engine's own default — is what keeps that agent working on a stock
    install. Without this the page would ship a default that silently breaks
    one of three shipped agents.
    """
    got = resolve_tier_model(Job.DRAFTING, Engine.V3, reachable=ALL_PROVIDERS)
    assert got is not None
    assert got.engine_default and got.tier is None
    assert got.provider is Provider.ANTHROPIC
    # Every tier the job could reach was tried and reported, not silently
    # swallowed — and only those: the ladder starts at the job's own tier and
    # never ascends, so a Standard job never reports skipping Heavy.
    assert [t for t, _ in got.skipped] == list(tier_chain(JOB_TIER[Job.DRAFTING]))
    assert {r for _, r in got.skipped} == {SKIP_ENGINE}


def test_the_floor_never_invents_an_unreachable_provider():
    """No Anthropic credential means v3 genuinely cannot run — say so."""
    assert resolve_tier_model(Job.DRAFTING, Engine.V3, reachable=GOOGLE_ONLY) is None


def test_the_floor_does_not_fire_when_a_tier_can_serve():
    got = resolve_tier_model(Job.DRAFTING, Engine.V3, tier_map=ANTHROPIC_MAP, reachable=ANTHROPIC_ONLY)
    assert got is not None and not got.engine_default and got.tier is Tier.STANDARD


# ---------------------------------------------------------------------------
# Modality — output, never input
# ---------------------------------------------------------------------------

def test_no_chat_model_claims_image_output():
    """Today's honest answer. When one does, the Images row re-resolves itself."""
    assert not any(model_emits(m, Modality.IMAGE) for m in ModelName)


def test_image_models_emit_images():
    from agents.models import ImageModel

    assert all(model_emits(m, Modality.IMAGE) for m in ImageModel)


# ---------------------------------------------------------------------------
# The credential-source vocabulary
#
# This is a contract, not a detail: the settings page renders `source` directly
# and a second copy of the mapping already rotted once — when `server` split
# into `env`/`cloud`, the provider tiles fell through to "No key set" while the
# tier rows two tabs away correctly said "From env". Pin the vocabulary here.
# ---------------------------------------------------------------------------

SOURCES = {"user", "stored", "env", "cloud", "subscription", "none"}


def test_provider_status_emits_only_known_sources(monkeypatch):
    from routes import providers as providers_route

    rows = providers_route.providers_status(user_keys={}, user=None, db=None)["providers"]
    assert {row["source"] for row in rows} <= SOURCES
    assert {row["id"] for row in rows} == {p.value for p in Provider}
    # reachable and source must never disagree.
    for row in rows:
        assert row["reachable"] is (row["source"] != "none")


def test_a_supplied_key_wins_over_everything_else():
    from routes import providers as providers_route

    rows = providers_route.providers_status(
        user_keys={Provider.OPENAI: "sk-test"}, user=None, db=None
    )["providers"]
    openai = next(row for row in rows if row["id"] == Provider.OPENAI.value)
    assert openai["source"] == "user"


def test_a_server_key_reads_as_env_locally_and_as_nothing_when_deployed(monkeypatch):
    """Same config field, opposite answers to 'can my runs use this'.

    On a laptop or a self-hosted box that key is the user's own, so it is a real
    way in. On the hosted deployment it is Duct's, and `resolve_provider_key`
    will not spend it — so the honest answer to a customer is that this provider
    is not reachable, and the tile asks for a key. Reporting `cloud` there was
    accurate about the config and a lie about what would happen next."""
    from routes import providers as providers_route

    class _Cfg:
        gemini_api_key = "g"
        openai_api_key = ""
        anthropic_api_key = ""
        openrouter_api_key = ""

        def __init__(self, local):
            self.duct_local = local
            self.app_env = "local" if local else "production"

    for local, expected in ((True, "env"), (False, "none")):
        monkeypatch.setattr(providers_route, "get_configs", lambda local=local: _Cfg(local))
        monkeypatch.setattr(providers_route, "claude_oauth_available", lambda: False)
        monkeypatch.setattr(
            providers_route, "allow_server_provider_keys", lambda local=local: local
        )
        rows = providers_route.providers_status(user_keys={}, user=None, db=None)["providers"]
        google = next(r for r in rows if r["id"] == Provider.GOOGLE_GENAI.value)
        assert google["source"] == expected
        assert google["reachable"] is (expected != "none")
