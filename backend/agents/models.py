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
    # OpenRouter is not a fourth SDK — it is the OpenAI-compatible chat
    # completions shape pointed at a different base URL. That shape is the most
    # durable interface in this stack (every provider implements it), which is
    # why the endpoint is a config value: override the base URL and the same
    # code path reaches Ollama, vLLM, llama.cpp, Together, or a self-hosted
    # gateway. See agents/core/ports — this is the model-transport port.
    OPENROUTER = "openrouter"


class ModelName(str, Enum):
    
    # OpenAI
    GPT_5_5 = "gpt-5.5"
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_MINI = "gpt-5-mini"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    
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
    # such ID — Opus 5 is natively 1M there — so LangChain (v1) and ADK (v2)
    # would 404 on it. Enforced by CLI_ONLY_MODELS below.
    CLAUDE_OPUS_1M = "claude-opus-5[1m]"

    # OpenRouter — vendor/slug form. A *curated default list*, not a whitelist:
    # OpenRouter fronts 500+ models, so resolve_engine_model passes an unknown
    # slug through verbatim rather than silently substituting a default. These
    # are the open-weight / long-tail models worth naming.
    OR_DEEPSEEK_CHAT = "deepseek/deepseek-chat"
    OR_QWEN3_235B = "qwen/qwen3-235b-a22b"
    OR_KIMI_K2 = "moonshotai/kimi-k2"
    OR_GLM_4_6 = "z-ai/glm-4.6"
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
    Provider.OPENROUTER: ModelName.OR_DEEPSEEK_CHAT,
}

# Default endpoint for each OpenAI-compatible provider. Overridable per install
# (config.openrouter_base_url) so the same transport reaches any compatible
# gateway — a local Ollama or vLLM included.
OPENAI_COMPATIBLE_BASE_URL: dict[Provider, str] = {
    Provider.OPENROUTER: "https://openrouter.ai/api/v1",
}


def langchain_provider(provider: Provider) -> str:
    """The ``model_provider`` string LangChain's init_chat_model expects.

    OpenAI-compatible providers resolve to ``"openai"`` — they are the OpenAI
    chat-completions wire format at a different base URL, not a distinct
    integration. Keeping the mapping here means call sites never special-case
    a provider, and adding another compatible gateway is one dict entry.
    """
    if provider in OPENAI_COMPATIBLE_BASE_URL:
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
    if provider in OPENAI_COMPATIBLE_BASE_URL:
        return {
            "api_key": api_key,
            "base_url": base_url or OPENAI_COMPATIBLE_BASE_URL[provider],
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
