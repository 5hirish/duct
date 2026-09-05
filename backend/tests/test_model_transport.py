"""The model-transport port (agents/core/ports).

Two shapes live behind one ``Provider`` enum, and these tests pin the seam
between them. A **gateway** fronts other vendors' models, so its endpoint is a
config value rather than a fixed vendor URL. A gateway with a first-party
LangChain integration (OpenRouter) gets it; one without is served as the OpenAI
chat-completions shape at its own base URL, which is the fallback every gateway
supports and the branch a future Ollama / vLLM / LiteLLM entry would take.

The pieces that differ between those two shapes are exactly what breaks
silently, so each has a test here: which ``model_provider`` string LangChain is
given, and which reasoning kwarg the resulting class actually accepts.
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
    GATEWAY_BASE_URL,
    NATIVE_GATEWAY_PROVIDERS,
    ModelName,
    Provider,
    get_api_key_kwargs,
    langchain_provider,
)


# ---------------------------------------------------------------------------
# Gateways: a native integration where one exists, the OpenAI shape otherwise
# ---------------------------------------------------------------------------

def test_openrouter_resolves_to_its_own_integration():
    """`langchain-openrouter` exists, so LangChain is told 'openrouter' and
    builds a ChatOpenRouter — not a ChatOpenAI aimed at their base URL."""
    assert langchain_provider(Provider.OPENROUTER) == "openrouter"


@pytest.mark.parametrize("provider", [Provider.OPENAI, Provider.GOOGLE_GENAI, Provider.ANTHROPIC])
def test_native_providers_keep_their_own_integration(provider: Provider):
    assert langchain_provider(provider) == provider.value


def test_openrouter_kwargs_carry_key_and_default_endpoint():
    kwargs = get_api_key_kwargs(Provider.OPENROUTER, "sk-or-test")
    assert kwargs == {
        "api_key": "sk-or-test",
        "base_url": "https://openrouter.ai/api/v1",
    }


def test_a_gateway_endpoint_is_overridable():
    """A gateway's endpoint stays a config value — a regional endpoint or a
    self-hosted OpenRouter-compatible proxy is a setting, not a code change.

    Narrower than it used to be, and deliberately so. This once asserted that
    the same override reached a local Ollama, which was true while OpenRouter
    was a ChatOpenAI aimed elsewhere. It is not true of ChatOpenRouter, which
    speaks OpenRouter's API: pointing it at `localhost:11434` would talk the
    wrong protocol to Ollama. Reaching a local model server is now a new
    ``GATEWAY_BASE_URL`` entry — which takes the OpenAI-shape branch — rather
    than a base-URL override on this one.
    """
    kwargs = get_api_key_kwargs(
        Provider.OPENROUTER, "k", base_url="https://openrouter.example.internal/api/v1"
    )
    assert kwargs["base_url"] == "https://openrouter.example.internal/api/v1"


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
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "z-ai/glm-5.3-flash") is ModelName.OR_GLM_5_3_FLASH


def test_unknown_openrouter_slug_passes_through_verbatim():
    """OpenRouter fronts 400+ models. Substituting a default would discard the
    model a bring-your-own-key customer explicitly chose — which is the feature."""
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "minimax/minimax-m2") == "minimax/minimax-m2"


def test_openrouter_model_without_slug_shape_still_falls_back():
    """A bare name is a typo, not a model id — fall back rather than guarantee
    an upstream 404."""
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "gpt5mini") is ModelName.OR_DEEPSEEK_V4_FLASH


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


def test_the_gateway_registry_is_consistent():
    """Three properties of one small table, checked together.

    A gateway's endpoint is a config value, so the registry must supply the
    default it is overriding — without it `base_url` resolves to empty and the
    client silently falls back to its own. A gateway with a first-party package
    is served by it; any other is served as the OpenAI shape, the branch a
    future Ollama / vLLM / LiteLLM entry takes. And `NATIVE_GATEWAY_PROVIDERS`
    refines `GATEWAY_BASE_URL` rather than standing beside it — a member missing
    from the base map would have no endpoint.
    """
    assert NATIVE_GATEWAY_PROVIDERS <= GATEWAY_BASE_URL.keys()
    for provider, url in GATEWAY_BASE_URL.items():
        assert url.startswith("http")
        expected = provider.value if provider in NATIVE_GATEWAY_PROVIDERS else "openai"
        assert langchain_provider(provider) == expected


# ---------------------------------------------------------------------------
# The thinking dial, per transport
#
# agents/thinking.py is provider-blind by design and emits LangChain's standard
# `reasoning_effort`. ChatOpenRouter does not accept it — it takes OpenRouter's
# unified `reasoning={"effort": …}` — and, worse, *accepts the wrong kwarg
# anyway* by forwarding it inside model_kwargs behind a warning. So the dial
# would silently stop working rather than fail. agents/core/lc translates at the
# transport boundary; these pin that.
# ---------------------------------------------------------------------------

def test_openrouter_gets_the_unified_reasoning_object():
    from agents.core.lc import _thinking_kwargs_for

    assert _thinking_kwargs_for(
        Provider.OPENROUTER, ModelName.OR_GLM_5_3_FLASH, "deep"
    ) == {"reasoning": {"effort": "high"}}


@pytest.mark.parametrize(
    "provider,model",
    [
        (Provider.ANTHROPIC, ModelName.CLAUDE_SONNET),
        (Provider.OPENAI, ModelName.GPT_5_MINI),
    ],
)
def test_direct_vendors_keep_the_standard_kwarg(provider: Provider, model: ModelName):
    from agents.core.lc import _thinking_kwargs_for

    assert _thinking_kwargs_for(provider, model, "deep") == {"reasoning_effort": "high"}


def test_a_model_with_no_dial_says_nothing_on_either_transport():
    """Absent is a real answer — it must not become `reasoning={"effort": ""}`."""
    from agents.core.lc import _thinking_kwargs_for

    assert _thinking_kwargs_for(Provider.OPENROUTER, ModelName.OR_QWEN3_7_FLASH, "deep") == {}


def test_the_dial_survives_construction_as_a_first_class_field():
    """The regression guard that matters: `reasoning` must land on the field,
    not in `model_kwargs`. A shunt there warns and reaches the API as junk."""
    import warnings

    from agents.core.lc import resolve_chat_model

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a model_kwargs shunt raises here
        llm = resolve_chat_model(
            Provider.OPENROUTER, ModelName.OR_GLM_5_3_FLASH, "sk-or-v1-t", thinking="deep"
        )
    assert llm.reasoning == {"effort": "high"}
    assert llm.model_kwargs == {}


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
        # A raw OpenRouter slug: 400+ models behind one key, so there is no basis
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
