"""Engine enum with per-engine defaults and supported model mappings.

Mirrors agents/models.py for the engine dimension. Setting GENERATE_ENGINE
is sufficient — provider and model default from the engine definition here,
so GENERATE_PROVIDER and GENERATE_MODEL become optional overrides.

Engine → default provider → default model:
  v1  (LangChain)          → google_genai → gemini-2.5-flash
  v2  (Google ADK)         → google_genai → gemini-2.5-flash
  v3  (Claude Agent SDK)   → anthropic    → claude-sonnet-4-6

Supported providers per engine:
  v1  all three providers (OpenAI, Google, Anthropic — all native in LangChain)
  v2  all three providers (OpenAI via LiteLLM prefix, Google + Anthropic native)
  v3  anthropic only (Claude Agent SDK does not support other providers natively)
"""

from __future__ import annotations

from enum import Enum

from agents.models import AgentEffort, ModelName, Provider


class Engine(str, Enum):
    V1 = "v1"  # LangChain
    V2 = "v2"  # Google ADK
    V3 = "v3"  # Claude Agent SDK


# Default provider for each engine when GENERATE_PROVIDER is unset
ENGINE_DEFAULT_PROVIDER: dict[Engine, Provider] = {
    Engine.V1: Provider.GOOGLE_GENAI,
    Engine.V2: Provider.GOOGLE_GENAI,
    Engine.V3: Provider.ANTHROPIC,
}

# Default model for each (engine, provider) pair when GENERATE_MODEL is unset
ENGINE_DEFAULT_MODEL: dict[tuple[Engine, Provider], ModelName] = {
    # v1 — LangChain (all providers native)
    (Engine.V1, Provider.GOOGLE_GENAI): ModelName.GEMINI_2_5_FLASH,
    (Engine.V1, Provider.ANTHROPIC):    ModelName.CLAUDE_SONNET,
    (Engine.V1, Provider.OPENAI):       ModelName.GPT_5_MINI,
    # v2 — Google ADK
    (Engine.V2, Provider.GOOGLE_GENAI): ModelName.GEMINI_2_5_FLASH,
    (Engine.V2, Provider.ANTHROPIC):    ModelName.CLAUDE_SONNET,
    (Engine.V2, Provider.OPENAI):       ModelName.GPT_5_MINI,
    # v3 — Claude Agent SDK (Anthropic only)
    (Engine.V3, Provider.ANTHROPIC):    ModelName.CLAUDE_SONNET,
}

# Which providers each engine supports
ENGINE_SUPPORTED_PROVIDERS: dict[Engine, frozenset[Provider]] = {
    Engine.V1: frozenset({Provider.OPENAI, Provider.GOOGLE_GENAI, Provider.ANTHROPIC}),
    Engine.V2: frozenset({Provider.OPENAI, Provider.GOOGLE_GENAI, Provider.ANTHROPIC}),
    Engine.V3: frozenset({Provider.ANTHROPIC}),
}

# Whether an engine can authenticate without an explicit API key. Only the
# Claude Agent SDK (v3) supports an OAuth/subscription token fallback; v1/v2
# (Gemini) require their provider API key. Used by the engine-status endpoint
# to decide between "needs_auth" (recoverable) and "inactive".
ENGINE_SUPPORTS_OAUTH: dict[Engine, bool] = {
    Engine.V1: False,
    Engine.V2: False,
    Engine.V3: True,
}

# Env var name that each engine's underlying framework reads for each provider.
# Used by v2 (ADK) and v3 (Claude Agent SDK) runners when setting env vars.
ENGINE_PROVIDER_ENV_VAR: dict[Engine, dict[Provider, str]] = {
    Engine.V1: {
        Provider.OPENAI:       "OPENAI_API_KEY",
        Provider.GOOGLE_GENAI: "GOOGLE_API_KEY",
        Provider.ANTHROPIC:    "ANTHROPIC_API_KEY",
    },
    Engine.V2: {
        # ADK reads standard names — different from the Duct config key GEMINI_API_KEY
        Provider.OPENAI:       "OPENAI_API_KEY",
        Provider.GOOGLE_GENAI: "GOOGLE_API_KEY",
        Provider.ANTHROPIC:    "ANTHROPIC_API_KEY",
    },
    Engine.V3: {
        Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    },
}

# Default effort level per engine (only meaningful for v3 / Claude Agent SDK)
ENGINE_DEFAULT_EFFORT: dict[Engine, AgentEffort | None] = {
    Engine.V1: None,
    Engine.V2: None,
    Engine.V3: AgentEffort.HIGH,
}

# Duct config attribute name → API key for each provider
PROVIDER_CONFIG_ATTR: dict[Provider, str] = {
    Provider.OPENAI:       "openai_api_key",
    Provider.GOOGLE_GENAI: "gemini_api_key",
    Provider.ANTHROPIC:    "anthropic_api_key",
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
) -> ModelName:
    """Resolve the model for a given engine + provider.

    Uses override if it's a valid ModelName; otherwise returns the engine's
    default model for that provider.
    """
    default = ENGINE_DEFAULT_MODEL.get(
        (engine, provider),
        ENGINE_DEFAULT_MODEL.get((engine, ENGINE_DEFAULT_PROVIDER[engine]), ModelName.GEMINI_2_5_FLASH),
    )
    if not override:
        return default
    try:
        return ModelName(override.strip())
    except ValueError:
        return default


def get_env_var_for_engine_provider(engine: Engine, provider: Provider) -> str | None:
    """Return the env var name that the engine's framework reads for this provider."""
    return ENGINE_PROVIDER_ENV_VAR.get(engine, {}).get(provider)
