"""Engine enum with per-engine defaults and supported model mappings.

Mirrors agents/models.py for the engine dimension. Setting GENERATE_ENGINE
is sufficient — provider and model default from the engine definition here,
so GENERATE_PROVIDER and GENERATE_MODEL become optional overrides.

Engine → default provider → default model:
  v1  (LangChain)          → google_genai → gemini-2.5-flash
  v3  (Claude Agent SDK)   → anthropic    → claude-sonnet-5

Supported providers per engine:
  v1  OpenAI, Google, Anthropic + OpenRouter — all four native in LangChain,
      OpenRouter via `langchain-openrouter` (one key, 400+ models). A gateway
      with no package of its own is still reachable as the OpenAI shape at its
      own base URL; see GATEWAY_BASE_URL in agents/models.py
  v3  anthropic only (Claude Agent SDK does not support other providers natively)

A v2 (Google ADK) engine existed until it was removed: nothing dispatched its
runner, and the UI offered it while silently serving v1. Its defaults were
identical to v1's, so `resolve_engine` folding a stored "v2" back to V1 changes
no behaviour.

Only v1 gets OpenRouter, and that asymmetry is the point: v3's harness is
provider-locked by design (anthropics/claude-agent-sdk-python#410, closed
`not planned`), which is why v1 is the target harness for bring-your-own-model.
"""

from __future__ import annotations

from enum import Enum

from agents.models import CLI_ONLY_MODELS, MODEL_FALLBACK, AgentEffort, ModelName, Provider


class Engine(str, Enum):
    V1 = "v1"  # LangChain
    V3 = "v3"  # Claude Agent SDK


# Default provider for each engine when GENERATE_PROVIDER is unset
ENGINE_DEFAULT_PROVIDER: dict[Engine, Provider] = {
    Engine.V1: Provider.GOOGLE_GENAI,
    Engine.V3: Provider.ANTHROPIC,
}

# Default model for each (engine, provider) pair when GENERATE_MODEL is unset
ENGINE_DEFAULT_MODEL: dict[tuple[Engine, Provider], ModelName] = {
    # v1 — LangChain (all providers native)
    (Engine.V1, Provider.GOOGLE_GENAI): ModelName.GEMINI_2_5_FLASH,
    (Engine.V1, Provider.ANTHROPIC):    ModelName.CLAUDE_SONNET,
    (Engine.V1, Provider.OPENAI):       ModelName.GPT_5_MINI,
    (Engine.V1, Provider.OPENROUTER):   ModelName.OR_DEEPSEEK_V4_FLASH,
    # v3 — Claude Agent SDK (Anthropic only)
    (Engine.V3, Provider.ANTHROPIC):    ModelName.CLAUDE_SONNET,
}

# Which providers each engine supports
ENGINE_SUPPORTED_PROVIDERS: dict[Engine, frozenset[Provider]] = {
    Engine.V1: frozenset({
        Provider.OPENAI, Provider.GOOGLE_GENAI, Provider.ANTHROPIC, Provider.OPENROUTER,
    }),
    Engine.V3: frozenset({Provider.ANTHROPIC}),
}

# Whether an engine can authenticate without an explicit API key. Only the
# Claude Agent SDK (v3) supports an OAuth/subscription token fallback; v1
# requires its provider's API key. Used by the engine-status endpoint
# to decide between "needs_auth" (recoverable) and "inactive".
ENGINE_SUPPORTS_OAUTH: dict[Engine, bool] = {
    Engine.V1: False,
    Engine.V3: True,
}

# Env var name that each engine's underlying framework reads for each provider.
# Used by the v3 (Claude Agent SDK) runner when setting env vars.
ENGINE_PROVIDER_ENV_VAR: dict[Engine, dict[Provider, str]] = {
    Engine.V1: {
        Provider.OPENAI:       "OPENAI_API_KEY",
        Provider.GOOGLE_GENAI: "GOOGLE_API_KEY",
        Provider.ANTHROPIC:    "ANTHROPIC_API_KEY",
        Provider.OPENROUTER:   "OPENROUTER_API_KEY",
    },
    Engine.V3: {
        Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    },
}

# Default effort level per engine (only meaningful for v3 / Claude Agent SDK)
ENGINE_DEFAULT_EFFORT: dict[Engine, AgentEffort | None] = {
    Engine.V1: None,
    Engine.V3: AgentEffort.HIGH,
}


def resolve_fallback_models(
    engine: Engine,
    provider: Provider,
    model: ModelName | str,
) -> tuple[ModelName, ...]:
    """Models to try when ``model`` errors, in order. Empty means "do not retry".

    The engine policy over ``agents/models.MODEL_FALLBACK``, which holds the
    mapping itself — the split is the same one the rest of this module keeps:
    ``models.py`` owns what a model *is*, ``engines.py`` owns which engine may
    use it. Call this rather than reading the dict.

    Only v1 gets a chain: v3's harness owns its own retries inside the CLI, so
    mounting one there would be a second, invisible retry loop layered on the
    SDK's.

    A raw OpenRouter slug (a ``str``, not a ``ModelName``) resolves to no chain.
    """
    if engine is not Engine.V1:
        return ()
    if not isinstance(model, ModelName):
        return ()
    candidates = MODEL_FALLBACK.get(model, ())
    supported = ENGINE_SUPPORTED_PROVIDERS.get(engine, frozenset())
    if provider not in supported:
        return ()
    # A CLI-only id can never be a fallback target on v1 — same rule as
    # resolve_engine_model, which is where that constraint is stated.
    return tuple(m for m in candidates if m not in CLI_ONLY_MODELS)


# Duct config attribute name → API key for each provider
PROVIDER_CONFIG_ATTR: dict[Provider, str] = {
    Provider.OPENAI:       "openai_api_key",
    Provider.GOOGLE_GENAI: "gemini_api_key",
    Provider.ANTHROPIC:    "anthropic_api_key",
    Provider.OPENROUTER:   "openrouter_api_key",
}


# ---------------------------------------------------------------------------
# Resolver helpers
# ---------------------------------------------------------------------------

def resolve_engine(name: str | None) -> Engine:
    """Resolve a string to an Engine enum, defaulting to V1."""
    if not name:
        return Engine.V1
    try:
        return Engine(name.lower().strip())
    except ValueError:
        return Engine.V1


def resolve_engine_provider(engine: Engine, override: str | None = None) -> Provider:
    """Resolve the provider for a given engine.

    Uses override if provided and supported; otherwise returns the engine's
    default provider. If the override is not supported by the engine, falls
    back to the engine default and the caller should warn.
    """
    if not override:
        return ENGINE_DEFAULT_PROVIDER[engine]
    try:
        candidate = Provider(override.lower().strip())
    except ValueError:
        return ENGINE_DEFAULT_PROVIDER[engine]
    if candidate not in ENGINE_SUPPORTED_PROVIDERS[engine]:
        return ENGINE_DEFAULT_PROVIDER[engine]
    return candidate


def resolve_engine_model(
    engine: Engine,
    provider: Provider,
    override: str | None = None,
) -> ModelName | str:
    """Resolve the model for a given engine + provider.

    Uses the override if it names a known ModelName; otherwise returns the
    engine's default for that provider.

    **OpenRouter is the exception, deliberately.** It fronts 400+ models, so the
    ModelName enum is a curated default list rather than a whitelist — silently
    substituting a default would throw away the model a bring-your-own-key
    customer explicitly asked for, which is the whole feature. An unrecognised
    ``vendor/slug`` is passed through verbatim and the gateway decides whether
    it exists. The slug shape is required so a typo'd bare name still falls back
    instead of becoming a guaranteed upstream 404.

    ``CLI_ONLY_MODELS`` (the ``[1m]`` context variants) are the mirror case:
    they are Claude Code model strings the Agent SDK understands and the
    Messages API does not, so v1 falls back to its default rather than
    forwarding one to LangChain.
    """
    default = ENGINE_DEFAULT_MODEL.get(
        (engine, provider),
        ENGINE_DEFAULT_MODEL.get((engine, ENGINE_DEFAULT_PROVIDER[engine]), ModelName.GEMINI_2_5_FLASH),
    )
    if not override:
        return default
    candidate = override.strip()
    try:
        resolved = ModelName(candidate)
    except ValueError:
        if provider == Provider.OPENROUTER and "/" in candidate:
            return candidate
        return default
    if resolved in CLI_ONLY_MODELS and engine is not Engine.V3:
        return default
    return resolved


def get_env_var_for_engine_provider(engine: Engine, provider: Provider) -> str | None:
    """Return the env var name that the engine's framework reads for this provider."""
    return ENGINE_PROVIDER_ENV_VAR.get(engine, {}).get(provider)
