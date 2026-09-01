"""The model-transport port (agents/core/ports).

OpenRouter is not a fourth SDK — it is the OpenAI-compatible chat-completions
shape at a different base URL. These tests pin that framing, because the value
of adopting the standard shape is that the endpoint becomes a config value:
the same code path reaches OpenRouter, Ollama, vLLM, or a self-hosted gateway.
"""

from __future__ import annotations

import pytest

from agents.engines import (
    ENGINE_PROVIDER_ENV_VAR,
    ENGINE_SUPPORTED_PROVIDERS,
    PROVIDER_CONFIG_ATTR,
    Engine,
    get_env_var_for_engine_provider,
    resolve_engine_model,
    resolve_engine_provider,
    resolve_fallback_models,
)
from agents.models import (
    MODEL_FALLBACK,
    OPENAI_COMPATIBLE_BASE_URL,
    ModelName,
    Provider,
    get_api_key_kwargs,
    langchain_provider,
)


# ---------------------------------------------------------------------------
# The OpenAI-compatible shape
# ---------------------------------------------------------------------------

def test_openrouter_resolves_to_the_openai_wire_format():
    """It is the OpenAI format, so LangChain must be told 'openai'."""
    assert langchain_provider(Provider.OPENROUTER) == "openai"


@pytest.mark.parametrize("provider", [Provider.OPENAI, Provider.GOOGLE_GENAI, Provider.ANTHROPIC])
def test_native_providers_keep_their_own_integration(provider: Provider):
    assert langchain_provider(provider) == provider.value


def test_openrouter_kwargs_carry_key_and_default_endpoint():
    kwargs = get_api_key_kwargs(Provider.OPENROUTER, "sk-or-test")
    assert kwargs == {
        "api_key": "sk-or-test",
        "base_url": "https://openrouter.ai/api/v1",
    }


def test_base_url_override_repoints_the_same_transport():
    """The payoff of adopting the standard: a local model is a config change.

    If this ever stops working, OpenRouter has quietly become a dependency
    rather than one interchangeable endpoint among many.
    """
    kwargs = get_api_key_kwargs(
        Provider.OPENROUTER, "ollama", base_url="http://localhost:11434/v1"
    )
    assert kwargs["base_url"] == "http://localhost:11434/v1"


@pytest.mark.parametrize(
    "provider,expected_key",
    [
        (Provider.OPENAI, "openai_api_key"),
        (Provider.GOOGLE_GENAI, "google_api_key"),
        (Provider.ANTHROPIC, "anthropic_api_key"),
    ],
)
def test_native_credential_kwargs_are_unchanged(provider: Provider, expected_key: str):
    """Regression guard — adding a provider must not disturb the existing three."""
    kwargs = get_api_key_kwargs(provider, "k")
    assert kwargs == {expected_key: "k"}
    assert "base_url" not in kwargs


# ---------------------------------------------------------------------------
# Model resolution — curated list, not a whitelist
# ---------------------------------------------------------------------------

def test_known_openrouter_slug_resolves_to_the_enum():
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "z-ai/glm-4.6") is ModelName.OR_GLM_4_6


def test_unknown_openrouter_slug_passes_through_verbatim():
    """OpenRouter fronts 500+ models. Substituting a default would discard the
    model a bring-your-own-key customer explicitly chose — which is the feature."""
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "minimax/minimax-m2") == "minimax/minimax-m2"


def test_openrouter_model_without_slug_shape_still_falls_back():
    """A bare name is a typo, not a model id — fall back rather than guarantee
    an upstream 404."""
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "gpt5mini") is ModelName.OR_DEEPSEEK_CHAT


def test_native_providers_do_not_pass_unknown_models_through():
    assert resolve_engine_model(Engine.V1, Provider.OPENAI, "made/up") is ModelName.GPT_5_MINI


# ---------------------------------------------------------------------------
# Engine support — the asymmetry is the whole argument
# ---------------------------------------------------------------------------

def test_v1_supports_openrouter():
    assert Provider.OPENROUTER in ENGINE_SUPPORTED_PROVIDERS[Engine.V1]
    assert resolve_engine_provider(Engine.V1, "openrouter") is Provider.OPENROUTER


def test_v3_cannot_take_openrouter_and_falls_back():
    """The Claude Agent SDK is provider-locked by design (upstream #410, closed
    `not planned`). That is why v1 is the target harness for BYO model — asking
    v3 for another provider must degrade, never silently appear to work."""
    assert Provider.OPENROUTER not in ENGINE_SUPPORTED_PROVIDERS[Engine.V3]
    assert resolve_engine_provider(Engine.V3, "openrouter") is Provider.ANTHROPIC


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider", list(Provider))
def test_every_provider_has_a_config_attribute(provider: Provider):
    assert provider in PROVIDER_CONFIG_ATTR


@pytest.mark.parametrize("provider", list(Provider))
def test_every_provider_supported_by_v1_has_an_env_var(provider: Provider):
    if provider not in ENGINE_SUPPORTED_PROVIDERS[Engine.V1]:
        pytest.skip(f"{provider.value} is not a v1 provider")
    assert get_env_var_for_engine_provider(Engine.V1, provider)
    assert provider in ENGINE_PROVIDER_ENV_VAR[Engine.V1]


def test_openai_compatible_registry_is_the_single_source_of_truth():
    """Anything in the compatible map must resolve to the OpenAI format and
    carry a default endpoint — that pairing is what makes the port work."""
    for provider, url in OPENAI_COMPATIBLE_BASE_URL.items():
        assert langchain_provider(provider) == "openai"
        assert url.startswith("http")


# ---------------------------------------------------------------------------
# Model fallback: the registry in agents/models.py and the policy over it in
# agents/engines.py. Same split as the rest of this file — models.py owns what a
# model *is*, engines.py owns which engine may use it.
# ---------------------------------------------------------------------------

def _family(model) -> str:
    """Provider family implied by a model id.

    Derived from the id rather than looked up, because `agents/models.py` has no
    provider→models registry — the grouping lives in enum comments, which a test
    cannot read.
    """
    value = getattr(model, "value", str(model))
    if "/" in value:
        return "openrouter"
    for prefix, family in (("claude", "anthropic"), ("gemini", "google"), ("gpt", "openai")):
        if value.startswith(prefix):
            return family
    return "unknown"


def test_no_fallback_ever_crosses_a_provider():
    """The invariant that keeps a run on the key the caller actually supplied.

    A typo here — a Gemini id under an Anthropic key — would not fail at import.
    It would fail at the worst moment: mid-run, on the retry meant to rescue the
    run, with an auth error the user cannot act on.
    """
    for source, targets in MODEL_FALLBACK.items():
        for target in targets:
            assert _family(target) == _family(source), (
                f"{source.value} falls back to {target.value}, a different provider"
            )


def test_the_fallback_chain_is_one_step_everywhere():
    """One step bounds the quality downgrade a user did not ask for."""
    for source, targets in MODEL_FALLBACK.items():
        assert len(targets) == 1, f"{source.value} has a {len(targets)}-step chain"


def test_no_fallback_pair_loops_back():
    """A → B → A would retry the model that just failed."""
    for source, targets in MODEL_FALLBACK.items():
        for target in targets:
            assert source not in MODEL_FALLBACK.get(target, ()), (
                f"{source.value} and {target.value} fall back to each other"
            )


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        (Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, (ModelName.CLAUDE_HAIKU,)),
        # Bottom of its family — nothing sensible to step down to.
        (Provider.ANTHROPIC, ModelName.CLAUDE_HAIKU, ()),
        (Provider.GOOGLE_GENAI, ModelName.GEMINI_2_5_FLASH, (ModelName.GEMINI_2_5_FLASH_LITE,)),
        # A raw OpenRouter slug: 500+ models behind one key, so there is no basis
        # for guessing what the caller would accept instead.
        (Provider.OPENROUTER, "vendor/some-model", ()),
        # CLI-only ids are unreachable from LangChain at all — same rule as
        # test_v3_cannot_take_openrouter_and_falls_back above.
        (Provider.ANTHROPIC, ModelName.CLAUDE_OPUS_1M, ()),
    ],
)
def test_fallback_resolution(provider, model, expected):
    assert resolve_fallback_models(Engine.V1, provider, model) == expected


@pytest.mark.parametrize("engine", [Engine.V3])
def test_only_v1_gets_a_fallback_chain(engine: Engine):
    """v3's harness already retries inside the CLI."""
    assert resolve_fallback_models(engine, Provider.ANTHROPIC, ModelName.CLAUDE_SONNET) == ()
