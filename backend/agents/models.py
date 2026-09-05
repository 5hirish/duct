"""Provider, model, and SDK tool enums with helper functions.

Follows the nomadtools agents/models.py pattern for provider-agnostic
model initialization via LangChain's init_chat_model().
"""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import NamedTuple


class Provider(str, Enum):
    OPENAI = "openai"
    GOOGLE_GENAI = "google_genai"
    ANTHROPIC = "anthropic"
    # OpenRouter runs on its own first-party integration (``langchain-openrouter``
    # → ``ChatOpenRouter``), not on ChatOpenAI-with-a-base-URL. It was the latter
    # until the native package existed, and the swap buys the things the plain
    # chat-completions shape has nowhere to put: per-provider routing preferences
    # (``openrouter_provider``), OpenRouter's unified ``reasoning`` parameter,
    # data-collection controls, and app-attribution headers.
    #
    # The compatible shape is still the port (see agents/core/ports) and still
    # the way any *other* gateway would arrive — Ollama, vLLM, llama.cpp, a
    # self-hosted LiteLLM. OpenRouter simply stopped being the thing standing in
    # for it. ``GATEWAY_BASE_URL`` / ``NATIVE_GATEWAY_PROVIDERS`` below is where
    # that split is written down.
    OPENROUTER = "openrouter"
    # xAI is a first-party vendor, not a gateway: LangChain resolves "xai" to
    # ``langchain-xai`` → ``ChatXAI``, so it needs no base-URL entry and takes
    # the native branch in ``langchain_provider``. Reachable as the OpenAI
    # shape at api.x.ai too, but the native package carries reasoning_effort
    # and xAI's server-side search as real fields rather than passthrough.
    XAI = "xai"


class ModelName(str, Enum):
    
    # OpenAI. Verified against the live /v1/models response. Unlike the Gemini
    # list nothing here was retired — every previous entry still serves and none
    # has an announced API shutdown — so this trim is curation, not repair.
    # The 5.6 family renamed the tiers: sol/terra/luna, no "mini" rung, which is
    # why GPT_5_MINI is the one older id kept (it is the engine default).
    GPT_5_6_SOL   = "gpt-5.6-sol"      # flagship — complex professional work
    GPT_5_6_TERRA = "gpt-5.6-terra"    # balances intelligence and cost
    GPT_5_6_LUNA  = "gpt-5.6-luna"     # cost-sensitive workloads
    GPT_5_MINI    = "gpt-5-mini"
    # Kept on purpose, not by omission — do not curate these away. They are
    # generations behind and the catalog lists the GPT-4 line as deprecated,
    # but both are still served with no announced shutdown.
    GPT_4O        = "gpt-4o"
    GPT_4O_MINI   = "gpt-4o-mini"
    
    # Google. Verified against the live ListModels response, not just the docs
    # — the published shutdown dates are "earliest possible" and drift both
    # ways (gemini-3.1-flash-lite-preview is still served past its date, while
    # gemini-3.1-flash-preview is already gone and was dropped from here).
    # The only current-generation Pro, and the Heavy rung of the shipped
    # default triple. Still a `-preview` id because Google has published no
    # stable 3.x Pro; verified against the live ListModels response and a real
    # generateContent call rather than taken from the docs.
    GEMINI_3_1_PRO_PREVIEW = "gemini-3.1-pro-preview"
    GEMINI_3_8_FLASH = "gemini-3.8-flash"
    GEMINI_3_5_FLASH_LITE = "gemini-3.5-flash-lite"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    
    # Anthropic
    # Anthropic's most capable widely released model, above the Opus tier and
    # priced accordingly ($10/$50 against Opus 5's $5/$25) — offered, not
    # defaulted to. Two behaviours differ from the rest of the family and both
    # are load-bearing here: thinking is always on (a `budget_tokens` config is
    # a 400, which is why it maps to the effort ladder like the other 5s), and
    # forced tool choice is rejected — `tool_choice: any` returns a 400. The
    # content enrichment pass forces exactly that through LangChain's
    # ToolStrategy, so on this model that pass degrades to local signals
    # instead of returning trends. See agents/content/enrichment.py.
    CLAUDE_FABLE = "claude-fable-5-1"
    CLAUDE_OPUS = "claude-opus-5"
    CLAUDE_SONNET = "claude-sonnet-5"
    CLAUDE_HAIKU = "claude-haiku-4-5"
    # v3 only. The [1m] suffix is a Claude Code / Agent SDK model string that
    # opts the CLI into the 1M-token context window. The Messages API has no
    # such ID — Opus 5 is natively 1M there — so LangChain (v1) would 404 on
    # it. Enforced by CLI_ONLY_MODELS below.
    CLAUDE_OPUS_1M = "claude-opus-5[1m]"

    # xAI. Verified against docs.x.ai: 500k context, $2/$6, and
    # `reasoning_effort` low/medium/high/xhigh — "Reasoning cannot be
    # disabled", so there is no off rung to offer. No fallback pair below:
    # it is the only Grok in the catalogue, and MODEL_FALLBACK never guesses
    # a target it was not given.
    GROK_4_6 = "grok-4.6"

    # OpenRouter — vendor/slug form. A *curated default list*, not a whitelist:
    # OpenRouter fronts 400+ models, so resolve_engine_model passes an unknown
    # slug through verbatim rather than silently substituting a default. These
    # are the open-weight / long-tail models worth naming.
    #
    # Refreshed against the live /api/v1/models catalogue. The previous
    # generation (deepseek-chat, qwen3-235b-a22b, kimi-k2, glm-4.6) all still
    # serve, so nothing here is repair — but each had been superseded by a
    # successor that is both cheaper and longer-context by roughly an order of
    # magnitude, which on this list is the entire point:
    #
    #   deepseek-chat      $0.26/$1.03  164k  →  v4-flash    $0.08/$0.16  1.0M
    #   qwen3-235b-a22b    $0.45/$1.82  131k  →  qwen3.8-flash $0.15/$0.47 1.0M
    #   glm-4.6            $0.43/$1.75  205k  →  glm-5.3-flash $0.07/$0.25 1.3M
    #   kimi-k2            $0.57/$2.30  131k  →  kimi-k3     $3.00/$15.00 1.0M
    #
    # kimi-k3 is the exception to the "cheaper and longer" pattern above: it is
    # ~6x the price of the k2.5 it replaces, bought with 4x the context. It is
    # here as the capable end of the open-weight list, not as a volume model.
    #
    # deepseek-v4-pro sits beside v4-flash rather than replacing it — same
    # vendor, same 1.0M context, ~10x the price for the reasoning tier. Two
    # rungs of one family is the point.
    #
    # All carry `tools` in supported_parameters; a slug that cannot tool-call
    # has no business here, since every Duct agent is a tool-calling agent.
    OR_DEEPSEEK_V4_FLASH = "deepseek/deepseek-v4-flash"
    OR_DEEPSEEK_V4_PRO = "deepseek/deepseek-v4-pro"
    OR_QWEN3_8_FLASH = "qwen/qwen3.8-flash"
    OR_KIMI_K3 = "moonshotai/kimi-k3"
    OR_GLM_5_3_FLASH = "z-ai/glm-5.3-flash"
    OR_CLAUDE_OPUS = "anthropic/claude-opus-5"
    OR_CLAUDE_SONNET = "anthropic/claude-sonnet-5"
    OR_GPT_5_MINI = "openai/gpt-5-mini"


class AgentTool(StrEnum):
    """Built-in Claude Agent SDK tool names passed to allowed_tools (audit v3).

    Per-agent tool names are NOT here — each agent type owns its own enum next
    to its tools/schema: see AuditTool (agents/audit/schema.py, the
    ``duct_crawl`` MCP server) and ContentTool (agents/content/schema.py, the
    LangChain-bound content tools).
    """

    ASK_USER_QUESTION = "AskUserQuestion"
    TODO_WRITE = "TodoWrite"
    WEB_SEARCH  = "WebSearch"         # SERP research, competitor discovery
    WEB_FETCH   = "WebFetch"          # fetch arbitrary URLs (e.g. competitor pages)
    AGENT = "Agent"
    READ = "Read"
    WRITE = "Write"
    EDIT = "Edit"
    BASH = "Bash"
    GREP = "Grep"
    GLOB = "Glob"
    NOTEBOOK_EDIT = "NotebookEdit"


class AgentPermissionMode(StrEnum):
    """Claude Agent SDK permission_mode values for ClaudeAgentOptions."""

    DEFAULT = "default"          # unmatched tools fall through to canUseTool
    DONT_ASK = "dontAsk"         # unmatched tools are hard-denied; canUseTool skipped (except AskUserQuestion)
    ACCEPT_EDITS = "acceptEdits" # file-edit tools auto-approved; others need canUseTool
    BYPASS = "bypassPermissions" # all tools approved; use only in fully controlled environments
    PLAN = "plan"                # read-only tools only; no file writes


class ThinkingMode(StrEnum):
    """Claude Agent SDK thinking type values for ClaudeAgentOptions.thinking.

    Pass as ThinkingConfigAdaptive(type=ThinkingMode.ADAPTIVE) — using the enum
    avoids bare string literals and ensures the SDK's TypedDict gets the required
    'type' key (ThinkingConfigAdaptive() with no args produces {} which raises
    KeyError: 'type' at CLI command build time).
    """

    ADAPTIVE = "adaptive"   # model decides thinking depth per turn
    ENABLED  = "enabled"    # fixed budget_tokens; pair with ThinkingConfigEnabled
    DISABLED = "disabled"   # no extended thinking


class AgentEffort(StrEnum):
    """Claude Agent SDK effort levels for ClaudeAgentOptions (v3 engine only).

    Controls how hard the model works before responding. Maps to the Claude CLI
    --effort flag introduced in claude-agent-sdk v0.1.36.

    LOW    — fastest, cheapest; good for simple lookups
    MEDIUM — balanced default
    HIGH   — deeper reasoning; recommended for complex analysis (e.g. SEO audit)
    XHIGH  — between HIGH and MAX; the sweet spot for coding/agentic work on
             Opus 5, Opus 4.8/4.7, Sonnet 5 and Fable 5. Falls back to HIGH on
             models that predate it (Opus 4.6, Sonnet 4.6 and earlier).
    MAX    — maximum effort; most expensive
    """

    LOW   = "low"
    MEDIUM = "medium"
    HIGH  = "high"
    XHIGH = "xhigh"
    MAX   = "max"


class ImageModel(str, Enum):
    """Image generation model IDs (Gemini image models via google-genai SDK).

    Imagen is gone: imagen-4.0-{generate,ultra-generate,fast-generate}-001 were
    retired on 2026-08-17 and Google's own replacement is gemini-3.1-flash-image
    — already the default below, so nothing here lost a capability. Their
    generate_images/edit_image call path went with them.

    gemini-2.5-flash-image is dropped for the same reason ahead of its
    2026-10-02 shutdown. Historical ContentAsset rows still carry these strings;
    that is fine, ImageAsset.model is a plain str and is never re-validated.
    """

    GEMINI_3_1_FLASH_IMAGE      = "gemini-3.1-flash-image"
    GEMINI_3_1_FLASH_LITE_IMAGE = "gemini-3.1-flash-lite-image"
    GEMINI_3_PRO_IMAGE          = "gemini-3-pro-image"


# gemini-3.1-flash-image: the high-efficiency, high-volume flash image model
# (per the Gemini image-generation docs) — the right default for slide gen.
DEFAULT_IMAGE_MODEL = ImageModel.GEMINI_3_1_FLASH_IMAGE


class AspectRatio(StrEnum):
    """Image aspect ratios accepted by the Gemini image models."""

    SQUARE_1_1     = "1:1"
    PORTRAIT_9_16  = "9:16"
    LANDSCAPE_16_9 = "16:9"
    PORTRAIT_3_4   = "3:4"
    LANDSCAPE_4_3  = "4:3"
    PORTRAIT_2_3   = "2:3"
    LANDSCAPE_3_2  = "3:2"
    PORTRAIT_4_5   = "4:5"
    LANDSCAPE_5_4  = "5:4"
    PORTRAIT_9_21  = "9:21"
    LANDSCAPE_21_9 = "21:9"
    PORTRAIT_3_5   = "3:5"
    LANDSCAPE_5_3  = "5:3"


# Models only the Claude Agent SDK (v3) accepts — see CLAUDE_OPUS_1M above.
# resolve_engine_model refuses to hand these to any other engine, so a stray
# GENERATE_MODEL=claude-opus-5[1m] degrades to the engine default instead of
# becoming a guaranteed upstream 404.
CLI_ONLY_MODELS: frozenset[ModelName] = frozenset({ModelName.CLAUDE_OPUS_1M})

# Default provider → model mapping
DEFAULT_MODELS = {
    Provider.OPENAI: ModelName.GPT_5_MINI,
    Provider.GOOGLE_GENAI: ModelName.GEMINI_2_5_FLASH,
    Provider.ANTHROPIC: ModelName.CLAUDE_SONNET,
    Provider.OPENROUTER: ModelName.OR_DEEPSEEK_V4_FLASH,
    Provider.XAI: ModelName.GROK_4_6,
}

# Where a run goes when its model will not answer — model data, so it lives
# here beside the enum it is written in. The *policy* over it (which engines get
# a chain at all, and whether the provider still matches) is the engine
# dimension and lives in agents/engines.resolve_fallback_models; nothing should
# read this dict directly.
#
# **Same provider, one step.** Two rules, both deliberate:
#
# * Same provider, because a fallback has to run on the key the caller handed
#   us. `service/auth.get_user_provider_keys` returns only the providers the
#   caller actually supplied a header for — normally exactly one — so a
#   cross-provider hop would have no credential, and reaching for Duct's own key
#   would move a customer's spend onto our account without asking.
# * One step, because a fallback is a quality downgrade the user did not choose.
#   Sonnet → Haiku still writes the brief. A longer ladder turns a transient 529
#   into a materially worse deliverable with no signal that it happened.
#
# Absent = no fallback, and the middleware is not mounted at all. That is the
# right answer for a model already at the bottom of its family, and for an
# unrecognised OpenRouter slug: OpenRouter fronts 400+ models, so there is no
# basis for guessing what a caller's chosen slug should degrade to, and
# silently substituting another vendor's model is worse than failing.
MODEL_FALLBACK: dict[ModelName, tuple[ModelName, ...]] = {
    # Anthropic
    ModelName.CLAUDE_FABLE:          (ModelName.CLAUDE_OPUS,),
    ModelName.CLAUDE_OPUS:           (ModelName.CLAUDE_SONNET,),
    ModelName.CLAUDE_SONNET:         (ModelName.CLAUDE_HAIKU,),
    # Google
    ModelName.GEMINI_3_1_PRO_PREVIEW: (ModelName.GEMINI_3_8_FLASH,),
    ModelName.GEMINI_3_8_FLASH:      (ModelName.GEMINI_2_5_FLASH,),
    ModelName.GEMINI_3_5_FLASH_LITE: (ModelName.GEMINI_2_5_FLASH_LITE,),
    ModelName.GEMINI_2_5_FLASH:      (ModelName.GEMINI_2_5_FLASH_LITE,),
    # OpenAI
    ModelName.GPT_5_6_SOL:           (ModelName.GPT_5_6_TERRA,),
    ModelName.GPT_5_6_TERRA:         (ModelName.GPT_5_6_LUNA,),
    ModelName.GPT_5_6_LUNA:          (ModelName.GPT_5_MINI,),
    ModelName.GPT_5_MINI:            (ModelName.GPT_4O_MINI,),
    ModelName.GPT_4O:                (ModelName.GPT_4O_MINI,),
}

# Gateways — providers that front other vendors' models and whose endpoint is
# therefore a config value rather than a fixed vendor URL. Overridable per
# install (config.openrouter_base_url) so the same code path reaches a
# self-hosted router or a local model server.
# Context windows, in tokens, as the providers publish them. This feeds the
# context gauge in the chat shell and nothing else: a stale number here makes
# the ring slightly wrong, never a request wrong, so it is a table rather than
# a live lookup. The default is the Claude window, the most common case; a
# model missing from the table still gets a gauge.
DEFAULT_CONTEXT_WINDOW = 200_000
CONTEXT_WINDOW: dict[ModelName, int] = {
    ModelName.GPT_5_6_SOL: 400_000,
    ModelName.GPT_5_6_TERRA: 400_000,
    ModelName.GPT_5_6_LUNA: 400_000,
    ModelName.GPT_5_MINI: 400_000,
    ModelName.GPT_4O: 128_000,
    ModelName.GPT_4O_MINI: 128_000,
    ModelName.GEMINI_3_1_PRO_PREVIEW: 1_000_000,
    ModelName.GEMINI_3_8_FLASH: 1_000_000,
    ModelName.GEMINI_3_5_FLASH_LITE: 1_000_000,
    ModelName.GEMINI_2_5_FLASH: 1_000_000,
    ModelName.GEMINI_2_5_FLASH_LITE: 1_000_000,
    ModelName.CLAUDE_FABLE: 1_000_000,
    ModelName.CLAUDE_OPUS: 200_000,
    ModelName.CLAUDE_SONNET: 200_000,
    ModelName.CLAUDE_HAIKU: 200_000,
    ModelName.CLAUDE_OPUS_1M: 1_000_000,
    ModelName.GROK_4_6: 500_000,
    ModelName.OR_DEEPSEEK_V4_FLASH: 1_000_000,
    ModelName.OR_DEEPSEEK_V4_PRO: 1_000_000,
    ModelName.OR_QWEN3_8_FLASH: 1_000_000,
    ModelName.OR_KIMI_K3: 1_000_000,
    ModelName.OR_GLM_5_3_FLASH: 1_300_000,
    ModelName.OR_CLAUDE_OPUS: 200_000,
    ModelName.OR_CLAUDE_SONNET: 200_000,
    ModelName.OR_GPT_5_MINI: 400_000,
}


class ModelPrice(NamedTuple):
    """USD per million tokens, as the provider lists them."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


# List prices, USD per million tokens, from the providers' pricing pages via
# models.dev on 2026-09-05. This feeds the cost figure beside the context
# gauge and nothing else: a stale price makes the figure slightly wrong, never
# a request wrong, so a table is right and a live lookup is not. A model that
# is missing here shows tokens without a dollar figure rather than a made-up
# one — on BYO keys the number is what the user actually pays, so a guess is
# worse than a blank.
PRICING: dict[ModelName, ModelPrice] = {
    ModelName.GPT_5_6_SOL: ModelPrice(4.0, 20.0, 0.4, 5.0),
    ModelName.GPT_5_6_TERRA: ModelPrice(2.0, 12.0, 0.2, 2.5),
    ModelName.GPT_5_6_LUNA: ModelPrice(0.2, 1.2, 0.02, 0.25),
    ModelName.GPT_5_MINI: ModelPrice(0.25, 2.0, 0.025),
    ModelName.GPT_4O: ModelPrice(2.5, 10.0, 1.25),
    ModelName.GPT_4O_MINI: ModelPrice(0.15, 0.6, 0.075),
    ModelName.GEMINI_3_1_PRO_PREVIEW: ModelPrice(2.0, 12.0, 0.2),
    ModelName.GEMINI_3_8_FLASH: ModelPrice(0.75, 3.75, 0.075),
    ModelName.GEMINI_3_5_FLASH_LITE: ModelPrice(0.3, 2.5, 0.03),
    ModelName.GEMINI_2_5_FLASH: ModelPrice(0.3, 2.5, 0.03),
    ModelName.GEMINI_2_5_FLASH_LITE: ModelPrice(0.1, 0.4, 0.01),
    ModelName.CLAUDE_FABLE: ModelPrice(10.0, 50.0, 0.25, 12.5),
    ModelName.CLAUDE_OPUS: ModelPrice(5.0, 25.0, 0.5, 6.25),
    ModelName.CLAUDE_SONNET: ModelPrice(2.0, 10.0, 0.2, 2.5),
    ModelName.CLAUDE_HAIKU: ModelPrice(1.0, 5.0, 0.1, 1.25),
    ModelName.CLAUDE_OPUS_1M: ModelPrice(5.0, 25.0, 0.5, 6.25),
    # Base rates. xAI doubles both above a 200k-token prompt; ModelPrice has
    # no tier for that, so a very long Grok run under-reports.
    ModelName.GROK_4_6: ModelPrice(2.0, 6.0, 0.5),
    ModelName.OR_DEEPSEEK_V4_FLASH: ModelPrice(0.08722, 0.17444, 0.017444),
    ModelName.OR_DEEPSEEK_V4_PRO: ModelPrice(0.9309, 1.8618, 0.077575),
    ModelName.OR_QWEN3_8_FLASH: ModelPrice(0.15, 0.47, 0.03),
    ModelName.OR_KIMI_K3: ModelPrice(3.0, 15.0, 0.3),
    ModelName.OR_GLM_5_3_FLASH: ModelPrice(0.075, 0.25, 0.015),
    ModelName.OR_CLAUDE_OPUS: ModelPrice(5.0, 25.0, 0.5, 6.25),
    ModelName.OR_CLAUDE_SONNET: ModelPrice(2.0, 10.0, 0.2, 2.5),
    ModelName.OR_GPT_5_MINI: ModelPrice(0.25, 2.0, 0.025),
}


def _model_key(model: "ModelName | str | None") -> "ModelName | None":
    if isinstance(model, ModelName):
        return model
    try:
        return ModelName(str(model))
    except ValueError:
        return None


def price_for(model: "ModelName | str | None") -> ModelPrice | None:
    """The price list for a model id, by enum member or raw string; ``None``
    for a model the table does not know."""
    key = _model_key(model)
    return PRICING.get(key) if key is not None else None


def cost_usd(
    model: "ModelName | str | None",
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float | None:
    """What one model call cost, or ``None`` when the model is not priced.

    ``input_tokens`` is LangChain's count, which *includes* the cached and
    cache-written tokens; those are billed at their own rates, so they are
    taken out of the input figure before it is priced.
    """
    price = price_for(model)
    if price is None:
        return None
    uncached = max(0, input_tokens - cache_read_tokens - cache_creation_tokens)
    total = (
        uncached * price.input
        + cache_read_tokens * price.cache_read
        + cache_creation_tokens * price.cache_write
        + output_tokens * price.output
    )
    return round(total / 1_000_000, 6)


def context_window_for(model: "ModelName | str | None") -> int:
    """The context window for a model id, by enum member or raw string.

    A provider may report the model it actually served (a fallback, a dated
    alias) rather than the one asked for; a string it does not know falls
    through to the default rather than failing the gauge.
    """
    if isinstance(model, ModelName):
        return CONTEXT_WINDOW.get(model, DEFAULT_CONTEXT_WINDOW)
    try:
        return CONTEXT_WINDOW.get(ModelName(str(model)), DEFAULT_CONTEXT_WINDOW)
    except ValueError:
        return DEFAULT_CONTEXT_WINDOW


GATEWAY_BASE_URL: dict[Provider, str] = {
    Provider.OPENROUTER: "https://openrouter.ai/api/v1",
}

# Of those, the ones with a first-party LangChain integration of their own.
# A gateway NOT listed here is served as the OpenAI chat-completions shape at
# its own base URL, which is the fallback every gateway supports — that is what
# a future Ollama / vLLM / LiteLLM entry would get, and it is why
# ``langchain_provider`` still has two branches with only one gateway in the
# table. Membership here is a claim that the package exists and is maintained,
# not a preference: see the ``langchain-openrouter`` note in pyproject.toml.
NATIVE_GATEWAY_PROVIDERS: frozenset[Provider] = frozenset({Provider.OPENROUTER})


def langchain_provider(provider: Provider) -> str:
    """The ``model_provider`` string LangChain's init_chat_model expects.

    A gateway with its own integration passes its own name through — LangChain
    resolves ``"openrouter"`` to ``langchain-openrouter``. A gateway without one
    resolves to ``"openai"``: it is the OpenAI chat-completions wire format at a
    different base URL, not a distinct integration. Keeping the mapping here
    means call sites never special-case a provider.
    """
    if provider in GATEWAY_BASE_URL and provider not in NATIVE_GATEWAY_PROVIDERS:
        return Provider.OPENAI.value
    return provider.value


def get_api_key_kwargs(
    provider: Provider,
    api_key: str,
    *,
    base_url: str = "",
) -> dict:
    """Credential (and endpoint) kwargs for the given provider.

    Passed as a constructor kwarg, never by mutating ``os.environ`` — a global
    mutation races across concurrent requests carrying different BYO keys, and
    lets a server-side key win over the user's.
    """
    # Both gateway shapes take the same two kwargs: ChatOpenRouter aliases its
    # `openrouter_api_key` / `openrouter_api_base` fields to `api_key` /
    # `base_url`, exactly as ChatOpenAI names them. So this branch does not need
    # to know which of the two a gateway is.
    if provider in GATEWAY_BASE_URL:
        return {
            "api_key": api_key,
            "base_url": base_url or GATEWAY_BASE_URL[provider],
        }
    if provider == Provider.OPENAI:
        return {"openai_api_key": api_key}
    if provider == Provider.GOOGLE_GENAI:
        return {"google_api_key": api_key}
    if provider == Provider.ANTHROPIC:
        return {"anthropic_api_key": api_key}
    if provider == Provider.XAI:
        return {"xai_api_key": api_key}
    return {}


def resolve_provider(name: str | None) -> Provider:
    """Resolve a string to a Provider enum, defaulting to GOOGLE_GENAI."""
    if not name:
        return Provider.GOOGLE_GENAI
    try:
        return Provider(name.lower().strip())
    except ValueError:
        return Provider.GOOGLE_GENAI


def resolve_model(name: str | None, provider: Provider) -> ModelName:
    """Resolve a string to a ModelName enum, defaulting per provider."""
    if not name:
        return DEFAULT_MODELS.get(provider, ModelName.GEMINI_2_5_FLASH)
    try:
        return ModelName(name.strip())
    except ValueError:
        return DEFAULT_MODELS.get(provider, ModelName.GEMINI_2_5_FLASH)


# Which provider serves a model id, by the shape of the id itself.
#
# Derived rather than tabulated on purpose. A dict would be a third list to
# keep in step with ModelName and MODEL_THINKING, and it would have no answer
# at all for the case that matters most: an OpenRouter slug Duct has never
# heard of. Vendor prefixes are stable — Anthropic has never shipped a model
# that is not `claude-*` — so the prefix *is* the fact.
#
# Order matters. The `/` test runs first because `anthropic/claude-opus-5` is
# an OpenRouter slug, not an Anthropic model: it bills through OpenRouter's key
# and reaches a different endpoint, and reading it as Anthropic would spend the
# wrong credential.
_PROVIDER_PREFIXES: tuple[tuple[str, Provider], ...] = (
    ("claude-", Provider.ANTHROPIC),
    ("gemini-", Provider.GOOGLE_GENAI),
    ("gpt-", Provider.OPENAI),
    ("o1-", Provider.OPENAI),
    ("o3-", Provider.OPENAI),
)


def provider_of(model: "ModelName | str") -> Provider | None:
    """The provider that serves this model id, or None when unrecognisable.

    None is a real answer, not a failure to default: a caller choosing a
    credential must not be handed a guess. ``agents/tiers.resolve_tier_model``
    treats it as "fall back to this tier's default model" rather than
    "attempt it against an arbitrary key".
    """
    name = str(getattr(model, "value", model) or "").strip().lower()
    if not name:
        return None
    if "/" in name:
        return Provider.OPENROUTER
    for prefix, provider in _PROVIDER_PREFIXES:
        if name.startswith(prefix):
            return provider
    return None


class Modality(StrEnum):
    """What a model can *emit*. Input modality is deliberately not modelled.

    The distinction is the whole reason this exists. Every chat model in the
    catalogue *accepts* images — that is how file upload already works — so an
    input table would be a column of True and would answer the wrong question.
    What the settings page needs to know is whether a chosen model can produce
    an image, because that decides whether the user has to pick a separate
    image model at all.
    """

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"


# What each model emits. Absent means text only, which is the honest default:
# as of this catalogue **no** chat model here generates images — that lives in
# the disjoint ``ImageModel`` enum, reached through a different SDK call path.
#
# The table exists anyway, and is checked anyway, because the resolution it
# feeds ("does any configured tier already cover images?") is three lines, and
# writing it now means the day a chat model gains image output the settings
# page re-resolves itself instead of needing a UI change.
MODEL_EMITS: dict[str, frozenset[Modality]] = {
    model.value: frozenset({Modality.TEXT, Modality.IMAGE}) for model in ImageModel
}


def model_emits(model: "ModelName | str", modality: Modality) -> bool:
    """True when this model can produce ``modality`` itself."""
    name = str(getattr(model, "value", model) or "").strip()
    return modality in MODEL_EMITS.get(name, frozenset({Modality.TEXT}))
