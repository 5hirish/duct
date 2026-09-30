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

import os

import pytest
from pydantic import BaseModel

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
    provider_of,
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


@pytest.mark.parametrize(
    ("provider", "saved", "runs_on"),
    [
        (Provider.ANTHROPIC, "claude-opus-5", ModelName.CLAUDE_OPUS),
        (Provider.ANTHROPIC, "claude-sonnet-5", ModelName.CLAUDE_SONNET),
        (Provider.OPENAI, "gpt-5.6-sol", ModelName.GPT_6_1_SOL),
        (Provider.OPENAI, "gpt-5.6-terra", ModelName.GPT_6_1_SOL),
        (Provider.OPENAI, "gpt-5.6-luna", ModelName.GPT_6_LUNA),
        (Provider.XAI, "grok-4.6", ModelName.GROK_4_7),
        (Provider.OPENROUTER, "anthropic/claude-opus-5", ModelName.OR_CLAUDE_OPUS),
        (Provider.OPENROUTER, "deepseek/deepseek-v4-pro", ModelName.OR_DEEPSEEK_V4_PRO),
        (Provider.OPENROUTER, "openai/gpt-5-mini", ModelName.OR_GPT_6_LUNA),
    ],
)
def test_a_saved_pick_of_a_retired_model_runs_on_its_successor(provider, saved, runs_on):
    """Not on the provider default: a Heavy pick of Opus 5 falling to Sonnet,
    or of GPT-5.6 Sol falling to gpt-5-mini, is a quiet downgrade of a choice
    the user made on purpose."""
    assert resolve_engine_model(Engine.V1, provider, saved) is runs_on


def _blended(price) -> float:
    """Three input tokens to one output, the usual way to rank model prices."""
    return (3 * price.input + price.output) / 4


def test_a_retired_model_never_moves_up_a_price_class():
    """GPT-5.6 Sol was the flagship, and GPT-6's flagship is Astra at $10/$50.
    A saved pick moves to Sol instead — an upgrade is a cost surprise.

    Blended, not output alone: an agent loop re-sends the thread every turn, so
    input is most of the bill. DeepSeek V4 Pro 0813 costs 6% more per output
    token than the preview and 30% less per input one; output alone called
    that a step up."""
    from agents.models import PRICING, RETIRED_MODELS

    for old_id, retired in RETIRED_MODELS.items():
        if retired.successor is not None:
            assert _blended(PRICING[retired.successor]) <= _blended(retired.price), old_id


def test_only_an_openrouter_slug_may_retire_without_a_successor():
    """OpenRouter passes an unknown slug through, so the pick still runs.
    Anywhere else an id with no successor falls to the provider default."""
    from agents.models import RETIRED_MODELS

    orphans = [old_id for old_id, retired in RETIRED_MODELS.items() if retired.successor is None]
    assert orphans, "the DeepSeek V4 Flash preview is one"
    assert all(provider_of(old_id) is Provider.OPENROUTER for old_id in orphans), orphans


def test_a_pick_whose_successor_costs_more_keeps_running_as_picked():
    """V4.1 Flash is the only Flash DeepSeek still serves and costs more per
    uncached token than the preview did, so a saved preview pick is not moved
    onto it: it runs on the preview, priced and windowed as the preview."""
    from agents.models import context_window_for, current_model_id, price_for

    slug = "deepseek/deepseek-v4-flash"
    assert current_model_id(slug) == slug
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, slug) == slug
    assert price_for(slug).output == 0.1526
    assert context_window_for(slug) == 1_000_000


def test_every_retired_id_left_the_catalogue():
    """An id still in ModelName is not retired; listing it would shadow it."""
    from agents.models import RETIRED_MODELS

    assert not set(RETIRED_MODELS) & {m.value for m in ModelName}


def test_a_saved_tier_map_reads_back_with_successors():
    """The settings page shows what will run, not an id it no longer lists."""
    from service.model_settings import _clean

    assert _clean({"heavy": "claude-opus-5", "light": "claude-haiku-4-5"}) == {
        "heavy": ModelName.CLAUDE_OPUS.value,
        "light": ModelName.CLAUDE_HAIKU.value,
    }


def _anthropic_payload(model, *, thinking: str = "", temperature: float = 1.0) -> dict:
    from langchain_core.messages import HumanMessage

    from agents.core.lc import resolve_chat_model

    llm = resolve_chat_model(Provider.ANTHROPIC, model, "sk-ant-t", temperature, thinking=thinking)
    return llm._get_request_payload([HumanMessage("hi")])


@pytest.mark.parametrize("model", [ModelName.CLAUDE_FABLE, ModelName.CLAUDE_OPUS, ModelName.CLAUDE_SONNET])
def test_a_bound_thinking_model_drops_a_stale_block_instead_of_failing(model):
    """Pruning, the seen-image swap and compaction all edit earlier turns. On
    these models that is a 400 for any account opened after 2026-08-31 unless
    the request says to drop the stale block instead."""
    from agents.core.lc import THINKING_BINDING_BETA

    payload = _anthropic_payload(model)
    assert payload["thinking"]["block_binding"] == {"prefix_mismatch_behavior": "drop_block"}
    assert payload["thinking"]["type"] == "adaptive"
    assert THINKING_BINDING_BETA in payload["betas"]


def test_the_reasoning_summary_shows_exactly_when_it_did_before():
    """langchain-anthropic asks for a summarised display only when an effort
    is set, and setting `thinking` ourselves switches that off — so it is
    restated, and no more often."""
    assert _anthropic_payload(ModelName.CLAUDE_SONNET, thinking="deep")["thinking"]["display"] == "summarized"
    assert "display" not in _anthropic_payload(ModelName.CLAUDE_SONNET)["thinking"]


def test_a_model_without_bound_thinking_is_sent_nothing_new():
    payload = _anthropic_payload(ModelName.CLAUDE_HAIKU, thinking="deep")
    assert payload.get("thinking") is None
    assert not payload.get("betas")


@pytest.mark.parametrize(
    ("provider", "model", "kept"),
    [
        (Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, False),
        (Provider.ANTHROPIC, ModelName.CLAUDE_OPUS, False),
        (Provider.OPENAI, ModelName.GPT_6_LUNA, False),
        (Provider.OPENROUTER, ModelName.OR_CLAUDE_OPUS, False),
        (Provider.ANTHROPIC, ModelName.CLAUDE_HAIKU, True),
        (Provider.GOOGLE_GENAI, ModelName.GEMINI_3_5_FLASH_LITE, True),
    ],
)
def test_a_temperature_reaches_only_a_model_that_takes_one(provider, model, kept):
    """The verify call asks for 0 on each provider's Light model. GPT-6 and
    the Claude 5 family refuse any temperature while they reason — a 400, or
    for Sonnet 5.5 a ValueError before the request leaves."""
    from agents.core.lc import resolve_chat_model

    llm = resolve_chat_model(provider, model, "k", temperature=0.0)
    assert (llm.temperature == 0.0) is kept


def test_unknown_openrouter_slug_passes_through_verbatim():
    """OpenRouter fronts 400+ models. Substituting a default would discard the
    model a bring-your-own-key customer explicitly chose — which is the feature."""
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "minimax/minimax-m2") == "minimax/minimax-m2"


def test_openrouter_model_without_slug_shape_still_falls_back():
    """A bare name is a typo, not a model id — fall back rather than guarantee
    an upstream 404."""
    assert resolve_engine_model(Engine.V1, Provider.OPENROUTER, "gpt5mini") is ModelName.OR_DEEPSEEK_V4_1_FLASH


def test_native_providers_do_not_pass_unknown_models_through():
    assert resolve_engine_model(Engine.V1, Provider.OPENAI, "made/up") is ModelName.GPT_5_MINI


# ---------------------------------------------------------------------------
# Engine support — the asymmetry is the whole argument
# ---------------------------------------------------------------------------

def test_v1_supports_openrouter():
    assert Provider.OPENROUTER in ENGINE_SUPPORTED_PROVIDERS[Engine.V1]
    assert resolve_engine_provider(Engine.V1, "openrouter") is Provider.OPENROUTER


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
        # ChatXAI carries reasoning_effort as a real field, so xAI needs no
        # translation at the transport boundary the way OpenRouter does.
        (Provider.XAI, ModelName.GROK_4_7),
    ],
)
def test_direct_vendors_keep_the_standard_kwarg(provider: Provider, model: ModelName):
    from agents.core.lc import _thinking_kwargs_for

    kwargs = _thinking_kwargs_for(provider, model, "deep")
    assert kwargs["reasoning_effort"] == "high"
    assert "reasoning" not in kwargs, "OpenRouter's object, not a direct vendor's"


def test_a_model_with_no_dial_says_nothing_on_either_transport():
    """Absent is a real answer — it must not become `reasoning={"effort": ""}`."""
    from agents.core.lc import _thinking_kwargs_for

    assert _thinking_kwargs_for(Provider.OPENROUTER, ModelName.OR_QWEN3_8_FLASH, "deep") == {}


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
# Structured output: which method each integration is asked for
# ---------------------------------------------------------------------------

class _Verdict(BaseModel):
    label: str = ""


def _bound(structured) -> dict:
    """What the structured runnable binds onto the model call."""
    return dict(structured.first.kwargs)


@pytest.mark.parametrize("model", [ModelName.CLAUDE_FABLE, ModelName.CLAUDE_SONNET, ModelName.CLAUDE_HAIKU])
def test_a_structured_call_on_claude_uses_claudes_own_structured_output(model: ModelName):
    """The integration's default forces a tool call: a 400 on Fable 5.1, and
    from langchain-anthropic 1.7.4 not forced at all there. Claude's own
    structured output constrains the reply on every model in the catalogue."""
    from agents.core.lc import resolve_chat_model, structured_output

    bound = _bound(structured_output(resolve_chat_model(Provider.ANTHROPIC, model, "sk-ant-t"), _Verdict))
    assert bound["output_config"]["format"]["type"] == "json_schema"
    assert "tool_choice" not in bound


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        (Provider.OPENAI, ModelName.GPT_6_LUNA),
        (Provider.GOOGLE_GENAI, ModelName.GEMINI_3_8_FLASH),
        (Provider.OPENROUTER, ModelName.OR_DEEPSEEK_V4_PRO),
        (Provider.XAI, ModelName.GROK_4_7),
    ],
)
def test_every_other_integration_keeps_its_own_default(provider: Provider, model: ModelName):
    """OpenAI and Gemini default to a JSON schema already; OpenRouter's hosts
    do not all accept one, so tool calling stays until measured live."""
    from agents.core.lc import resolve_chat_model, structured_output

    llm = resolve_chat_model(provider, model, "AIza-t" if provider is Provider.GOOGLE_GENAI else "sk-t")
    assert _bound(structured_output(llm, _Verdict)) == _bound(llm.with_structured_output(_Verdict))


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
        (Provider.GOOGLE_GENAI, ModelName.GEMINI_3_8_FLASH, (ModelName.GEMINI_3_5_FLASH_LITE,)),
        # Bottom of the Gemini family since 2.5 Flash-Lite was retired.
        (Provider.GOOGLE_GENAI, ModelName.GEMINI_3_5_FLASH_LITE, ()),
        # A raw OpenRouter slug: 400+ models behind one key, so there is no basis
        # for guessing what the caller would accept instead.
        (Provider.OPENROUTER, "vendor/some-model", ()),
    ],
)
def test_fallback_resolution(provider, model, expected):
    assert resolve_fallback_models(Engine.V1, provider, model) == expected


@pytest.mark.skipif(
    not os.environ.get("XAI_API_KEY"),
    reason="XAI_API_KEY not set — live Grok skipped",
)
@pytest.mark.live
def test_live_grok_accepts_the_top_rung_of_the_ladder_we_publish():
    """Everything Duct claims about Grok came from docs.x.ai, not from a call.

    This is what would catch a wrong model id or an effort value xAI rejects —
    `xhigh` in particular, which the docs say arrived with 4.6 and which older
    Groks silently downgrade rather than refuse. Costs a fraction of a cent.
    """
    from agents.core.lc import resolve_chat_model

    llm = resolve_chat_model(
        Provider.XAI, ModelName.GROK_4_7, os.environ["XAI_API_KEY"], thinking="exhaustive"
    )
    reply = llm.invoke("Reply with the single word: ok")
    assert (reply.text or "").strip()


# ---------------------------------------------------------------------------
# The catalogue is only as true as the last generate call. ListModels kept
# listing gemini-2.5-flash-lite after generateContent started answering 404
# "no longer available to new users", and that id was the fallback sibling
# every Gemini plan run researched on. One tiny call per id, per provider
# with a key, is what would have caught it.
# ---------------------------------------------------------------------------


def _catalogue_key(provider: Provider) -> str:
    from config import get_configs
    from agents.engines import ENGINE_PROVIDER_ENV_VAR, PROVIDER_CONFIG_ATTR

    env_var = ENGINE_PROVIDER_ENV_VAR[Engine.V1].get(provider, "")
    return os.environ.get(env_var, "") or getattr(get_configs(), PROVIDER_CONFIG_ATTR[provider], "") or ""


def _catalogue_ids(provider: Provider) -> list[ModelName]:
    from agents.models import provider_of

    return [m for m in ModelName if provider_of(m) is provider]


@pytest.mark.live
@pytest.mark.parametrize("provider", sorted(ENGINE_SUPPORTED_PROVIDERS[Engine.V1], key=lambda p: p.value))
def test_live_every_catalogue_id_still_answers(provider: Provider):
    """A retired id fails here, not in a customer's plan run."""
    from agents.core.lc import resolve_chat_model

    key = _catalogue_key(provider)
    if not key:
        pytest.skip(f"no {provider.value} key — catalogue liveness skipped")
    dead: dict[str, str] = {}
    for model in _catalogue_ids(provider):
        try:
            resolve_chat_model(provider, model, key).invoke("Reply with the single word: ok")
        except Exception as exc:  # noqa: BLE001 - collected, then reported together
            dead[model.value] = str(exc)[:160]
    assert not dead, f"{provider.value} ids the provider no longer serves: {dead}"


@pytest.mark.live
@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI, Provider.XAI])
def test_live_a_tier_default_calls_a_tool_while_it_reasons(provider: Provider):
    """Every Duct agent is a tool-calling agent, and the 2026-09-29 defaults
    each changed the request that carries a tool: GPT-6 moves function calling
    to the Responses API once reasoning is on, and the Claude 5.5 models carry
    the thinking-binding beta and a summarised display. A plain "reply ok"
    exercises neither, so this makes one reasoning turn with one tool per rung."""
    from langchain_core.tools import tool

    from agents.core.lc import resolve_chat_model
    from agents.tiers import PROVIDER_TRIPLES, Tier

    key = _catalogue_key(provider)
    if not key:
        pytest.skip(f"no {provider.value} key — tool-call liveness skipped")

    @tool
    def lookup_weather(city: str) -> str:
        """The current weather in a city."""
        return "sunny"

    silent: list[str] = []
    for model in {PROVIDER_TRIPLES[provider][tier] for tier in (Tier.HEAVY, Tier.LIGHT)}:
        llm = resolve_chat_model(provider, model, key, thinking="balanced").bind_tools([lookup_weather])
        reply = llm.invoke("What is the weather in Valencia right now? Use the tool.")
        if not reply.tool_calls:
            silent.append(model.value)
    assert not silent, f"answered without calling the tool: {silent}"
