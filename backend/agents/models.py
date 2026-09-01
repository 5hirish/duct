"""Provider, model, and SDK tool enums with helper functions.

Follows the nomadtools agents/models.py pattern for provider-agnostic
model initialization via LangChain's init_chat_model().
"""

from __future__ import annotations

from enum import Enum, StrEnum


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
    GEMINI_3_7_FLASH = "gemini-3.7-flash"
    GEMINI_3_5_FLASH_LITE = "gemini-3.5-flash-lite"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    
    # Anthropic
    CLAUDE_OPUS = "claude-opus-5"
    CLAUDE_SONNET = "claude-sonnet-5"
    CLAUDE_HAIKU = "claude-haiku-4-5"
    # v3 only. The [1m] suffix is a Claude Code / Agent SDK model string that
    # opts the CLI into the 1M-token context window. The Messages API has no
    # such ID — Opus 5 is natively 1M there — so LangChain (v1) would 404 on
    # it. Enforced by CLI_ONLY_MODELS below.
    CLAUDE_OPUS_1M = "claude-opus-5[1m]"

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
    #   qwen3-235b-a22b    $0.45/$1.82  131k  →  qwen3.7-flash $0.03/$0.13 1.0M
    #   glm-4.6            $0.43/$1.75  205k  →  glm-5.3-flash $0.07/$0.25 1.3M
    #   kimi-k2            $0.57/$2.30  131k  →  kimi-k2.5   $0.45/$2.25  262k
    #
    # All four carry `tools` in supported_parameters; a slug that cannot tool-call
    # has no business here, since every Duct agent is a tool-calling agent.
    OR_DEEPSEEK_V4_FLASH = "deepseek/deepseek-v4-flash"
    OR_QWEN3_7_FLASH = "qwen/qwen3.7-flash"
    OR_KIMI_K2_5 = "moonshotai/kimi-k2.5"
    OR_GLM_5_3_FLASH = "z-ai/glm-5.3-flash"
    OR_CLAUDE_OPUS = "anthropic/claude-opus-5"
    OR_CLAUDE_SONNET = "anthropic/claude-sonnet-5"
    OR_GPT_5_MINI = "openai/gpt-5-mini"


class AgentTool(StrEnum):
    """Built-in Claude Agent SDK tool names passed to allowed_tools.

    Per-agent MCP tool names are NOT here — each agent type owns its own enum
    next to its tools/schema: see AuditTool (agents/audit/schema.py, server
    ``duct_crawl``) and ContentTool (agents/content/schema.py, ``duct_content``).
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
    ModelName.CLAUDE_OPUS:           (ModelName.CLAUDE_SONNET,),
    ModelName.CLAUDE_SONNET:         (ModelName.CLAUDE_HAIKU,),
    # Google
    ModelName.GEMINI_3_7_FLASH:      (ModelName.GEMINI_2_5_FLASH,),
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
