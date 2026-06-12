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


class ModelName(str, Enum):
    # OpenAI
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_MINI = "gpt-5-mini"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    # Google
    GEMINI_3_1_FLASH = "gemini-3.1-flash-preview"
    GEMINI_3_1_FLASH_LITE = "gemini-3.1-flash-lite-preview"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    # Anthropic
    CLAUDE_SONNET = "claude-sonnet-4-6"
    CLAUDE_HAIKU = "claude-haiku-4-5-20251001"


class AgentTool(StrEnum):
    """Built-in Claude Agent SDK tool names passed to allowed_tools."""

    ASK_USER_QUESTION = "AskUserQuestion"
    TODO_WRITE = "TodoWrite"
    FETCH_PAGES          = "mcp__duct_crawl__FetchPages"          # in-process MCP tool: use namespaced format
    SUBMIT_AUDIT_REPORT  = "mcp__duct_crawl__SubmitAuditReport"   # template mode only — chat-revision resubmit
    START_AUDIT_REPORT     = "mcp__duct_crawl__StartAuditReport"     # template: incremental build, step 1
    ADD_AUDIT_CATEGORY     = "mcp__duct_crawl__AddAuditCategory"     # template: incremental build, step 2 (×9)
    FINALIZE_AUDIT_REPORT  = "mcp__duct_crawl__FinalizeAuditReport"  # template: incremental build, step 3
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
    XHIGH  — Opus 4.7-specific extended effort; falls back to HIGH on other models
    MAX    — maximum effort; most expensive
    """

    LOW   = "low"
    MEDIUM = "medium"
    HIGH  = "high"
    XHIGH = "xhigh"
    MAX   = "max"


class ImageModel(str, Enum):
    """Image generation model IDs (Gemini + Imagen via google-genai SDK)."""

    GEMINI_3_1_FLASH_IMAGE_PREVIEW = "gemini-3.1-flash-image-preview"
    GEMINI_3_PRO_IMAGE_PREVIEW     = "gemini-3-pro-image-preview"
    GEMINI_2_5_FLASH_IMAGE         = "gemini-2.5-flash-image"
    IMAGEN_4_GENERATE_001          = "imagen-4.0-generate-001"
    IMAGEN_4_ULTRA_GENERATE_001    = "imagen-4.0-ultra-generate-001"
    IMAGEN_4_FAST_GENERATE_001     = "imagen-4.0-fast-generate-001"


DEFAULT_IMAGE_MODEL = ImageModel.GEMINI_3_1_FLASH_IMAGE_PREVIEW


class Platform(StrEnum):
    """Publishing channels — values match the PostBridge v1 API platform names."""

    TIKTOK          = "tiktok"
    INSTAGRAM       = "instagram"
    YOUTUBE         = "youtube"
    LINKEDIN        = "linkedin"
    TWITTER         = "twitter"
    FACEBOOK        = "facebook"
    THREADS         = "threads"
    BLUESKY         = "bluesky"
    PINTEREST       = "pinterest"
    GOOGLE_BUSINESS = "google_business"


class AspectRatio(StrEnum):
    """Image aspect ratios accepted by Gemini/Imagen."""

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


# Default provider → model mapping
DEFAULT_MODELS = {
    Provider.OPENAI: ModelName.GPT_5_MINI,
    Provider.GOOGLE_GENAI: ModelName.GEMINI_2_5_FLASH,
    Provider.ANTHROPIC: ModelName.CLAUDE_SONNET,
}


def get_api_key_kwargs(provider: Provider, api_key: str) -> dict:
    """Return the correct keyword argument for the given provider."""
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
