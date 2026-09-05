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

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from agents.models import CLI_ONLY_MODELS, MODEL_FALLBACK, AgentEffort, ModelName, Provider

logger = logging.getLogger(__name__)


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
        Provider.XAI,
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
        Provider.XAI:          "XAI_API_KEY",
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
    Provider.XAI:          "xai_api_key",
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


# ---------------------------------------------------------------------------
# Whose key pays for a run
# ---------------------------------------------------------------------------
#
# Every LLM credential a run spends comes through resolve_provider_key below.
# That is the point of putting it here rather than at each call site: a run
# billed to Duct's own Console account is a policy decision, and a policy that
# lives in six copies of `getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "")` is
# one that will be reintroduced by the next agent to need a key.
#
# Grepping for that getattr is the standing audit — outside this module it
# should return nothing but the settings/status readers, which ask whether a
# key exists and never spend one.


class ProviderKeyRequired(RuntimeError):
    """No credential this run is allowed to spend.

    Carries the provider so the API layer can turn it into a 402 the browser
    can act on — the Providers dialog for that provider — rather than a 500
    that reads like an outage.
    """

    def __init__(self, provider: Provider | str, detail: str = "") -> None:
        self.provider = getattr(provider, "value", str(provider))
        super().__init__(
            detail
            or f"No {self.provider} API key for this request. Add your own key in Settings → Providers."
        )


@dataclass(frozen=True)
class ProviderKey:
    """A resolved credential and, just as importantly, whose account it is."""

    key: str
    provider: Provider
    #: ``user``  — an X-Provider-* header on this request
    #: ``stored``— this user's saved, encrypted key
    #: ``env``   — this instance's env file (desktop / self-hosted: the user's own)
    #: ``cloud`` — Duct's hosted key; our account is paying
    #: ``subscription`` — the operator's Claude subscription on this machine
    source: str

    @property
    def billed_to_duct(self) -> bool:
        """True when this run costs Duct money. Log it; it should be rare."""
        return self.source in ("cloud", "subscription")


def resolve_provider_key(
    provider: Provider,
    user_keys: Mapping[Provider, str] | None = None,
    *,
    stored_keys: Mapping[Provider, str] | None = None,
    duct_pays: bool = False,
) -> ProviderKey:
    """The key this run may spend, in precedence order, or raise.

    1. ``user_keys``   — the caller's ``X-Provider-*`` header for this request
    2. ``stored_keys`` — their saved encrypted key (background jobs have no
       request to carry a header, so this is the only BYOK they can have)
    3. this instance's env key — **only** when ``allow_server_provider_keys()``
       says the env file belongs to the user running it, or the call site
       explicitly declared ``duct_pays``
    4. the Claude subscription, under the same gate and for the same reason

    ``duct_pays`` is for flows Duct deliberately funds — the lead-magnet teaser
    audit is demand gen, not a customer's run. Pass it as an expression at the
    call site (``duct_pays=req.lead_magnet``) so the condition stays readable.

    Kept free of any DB or request import: the caller merges what it has and
    this decides. ``service/provider_keys.py`` is the piece that loads stored
    keys, and it is the only thing that needs a session.
    """
    from config import allow_server_provider_keys, claude_oauth_available, get_configs

    supplied = (user_keys or {}).get(provider, "")
    if supplied and supplied.strip():
        return ProviderKey(supplied.strip(), provider, "user")

    saved = (stored_keys or {}).get(provider, "")
    if saved and saved.strip():
        return ProviderKey(saved.strip(), provider, "stored")

    cfg = get_configs()
    may_use_ours = duct_pays or allow_server_provider_keys()
    if not may_use_ours:
        # The whole reason this module exists. There IS a key in the env on the
        # hosted deployment and we are declining to spend it.
        raise ProviderKeyRequired(provider)

    server_key = (getattr(cfg, PROVIDER_CONFIG_ATTR.get(provider, ""), "") or "").strip()
    if server_key:
        # Same field, two different answers to "who is paying" — see
        # routes/providers.providers_status, which draws the same distinction.
        local = bool(cfg.duct_local) or cfg.app_env == "local"
        return ProviderKey(server_key, provider, "env" if local else "cloud")

    # v3's harness can authenticate with no key at all. That is the operator's
    # own subscription, so it sits behind the same gate as the env key rather
    # than being a way around it.
    if provider is Provider.ANTHROPIC and claude_oauth_available():
        return ProviderKey("", provider, "subscription")

    raise ProviderKeyRequired(provider)


# ---------------------------------------------------------------------------
# One resolver for "which model, on whose key" — shared by every V1 runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunModel:
    """Everything a V1 runner needs to open a model: provider, model, key."""

    provider: Provider
    model: ModelName | str
    api_key: str
    #: The artifact summariser still runs on the Agent SDK, so only an
    #: Anthropic key works there — a run on another provider persists its
    #: artifacts without a digest. Empty when that is the case.
    summary_key: str


def resolve_run_model(
    engine_override: str = "",
    user_keys: Mapping[Provider, str] | None = None,
    stored_keys: Mapping[Provider, str] | None = None,
    *,
    log_prefix: str = "agent",
) -> RunModel:
    """Engine → provider → model → key, for a run on the LangChain harness.

    Lived in ``agents/insights/setup.py`` until content became the second
    runner that needed it; the membership gate and the memory blocks stayed
    there because they are insights-shaped, this is not. The rules:

    * ``user_keys`` are per-request bring-your-own keys from the ``X-Provider-*``
      headers; ``stored_keys`` are the same user's saved keys, which is all a
      background worker can have. A caller's key wins over the server's for
      the *resolved* provider only — an OpenAI key someone supplied must never
      be spent on a Gemini call.
    * A caller's key can also *choose* the provider, in the one case where that
      is unambiguous: the operator expressed no preference (``GENERATE_PROVIDER``
      unset) and the caller supplied exactly one key. Nobody pastes an
      OpenRouter key hoping to be billed for Gemini. Two keys is not a
      preference, so that case keeps the engine default rather than guessing.
    * Whether the server's own key may be spent at all is decided by
      ``resolve_provider_key``, which fails closed on the hosted deployment.
      ``ProviderKeyRequired`` propagates deliberately: "you have not connected
      a key" is a 402 the browser can act on, not a 500.

    The engine override selects a provider/model *within* V1: V1 is the only
    harness the session runners implement, so a stored ``"v3"`` preference
    resolves to its Anthropic default rather than a different runner.
    """
    from config import get_configs

    cfg = get_configs()
    engine = resolve_engine(engine_override or cfg.generate_engine or "v1")
    provider = resolve_engine_provider(engine, cfg.generate_provider or None)
    model_override = cfg.generate_model or None
    # A saved key is as much "the caller asked for this provider" as a header
    # one — the only difference is that it survived a page refresh.
    byo = {**(stored_keys or {}), **(user_keys or {})}
    if not cfg.generate_provider and len(byo) == 1:
        (candidate,) = byo.keys()
        if candidate in ENGINE_SUPPORTED_PROVIDERS.get(engine, frozenset()):
            # GENERATE_MODEL goes with the provider the operator picked, so it
            # is dropped along with it — a Gemini model id forwarded to
            # OpenRouter is a guaranteed 404, and the engine default for the
            # new provider is the only id known to fit.
            if candidate is not provider:
                model_override = None
            provider = candidate
    model = resolve_engine_model(engine, provider, model_override)
    if isinstance(model, ModelName) and model in CLI_ONLY_MODELS:
        # A stored "v3" preference resolves its model under V3's rules, which
        # allow the [1m] CLI id; this run is on LangChain, where that id 404s.
        model = resolve_engine_model(Engine.V1, provider, None)
    resolved = resolve_provider_key(provider, user_keys, stored_keys=stored_keys)
    if resolved.billed_to_duct:
        logger.info("%s: run billed to Duct (%s/%s)", log_prefix, provider.value, resolved.source)
    api_key = resolved.key
    summary_key = api_key if getattr(provider, "value", str(provider)) == "anthropic" else ""
    return RunModel(provider=provider, model=model, api_key=api_key, summary_key=summary_key)
