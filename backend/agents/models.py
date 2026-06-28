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
    XAI = "xai"
    BYTE_PLUS = "byte_plus"

class ModelName(str, Enum):
    
    # OpenAI
    GPT_5_5 = "gpt-5.5"
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_MINI = "gpt-5-mini"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    
    # Google
    GEMINI_3_5_FLASH = "gemini-3.5-flash"
    GEMINI_3_1_FLASH = "gemini-3.1-flash-preview"
    GEMINI_3_1_FLASH_LITE = "gemini-3.1-flash-lite"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    
    # Anthropic
    CLAUDE_OPUS_4_8 = "claude-opus-4-8"
    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"


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
    XHIGH  — Opus 4.7-specific extended effort; falls back to HIGH on other models
    MAX    — maximum effort; most expensive
    """

    LOW   = "low"
    MEDIUM = "medium"
    HIGH  = "high"
    XHIGH = "xhigh"
    MAX   = "max"


class ImageModel(str, Enum):
    """Image generation model IDs (Gemini via google-genai SDK).

    The Imagen 4 endpoints (imagen-4.0-generate/ultra/fast-001) were removed —
    Google discontinues them on 2026-08-17, with gemini-3.1-flash-image as the
    sole migration path (now DEFAULT_IMAGE_MODEL below).
    """

    GEMINI_3_1_FLASH_IMAGE = "gemini-3.1-flash-image"
    GEMINI_3_PRO_IMAGE     = "gemini-3-pro-image"
    GEMINI_2_5_FLASH_IMAGE = "gemini-2.5-flash-image"


# gemini-3.1-flash-image: the high-efficiency, high-volume flash image model
# (per the Gemini image-generation docs) — the right default for slide gen.
DEFAULT_IMAGE_MODEL = ImageModel.GEMINI_3_1_FLASH_IMAGE


class VideoModel(str, Enum):
    """Video-generation model IDs, across providers (see video_provider_for).

    Veo (Google, google-genai generate_videos): 3.1 supports referenceImages
    (subject consistency) + first+last-frame interpolation; preview ids may be
    allowlisted/billed; the 3.0 ids are deprecated.
    Grok (xAI Imagine, SDK xai-sdk): image-to-video with native audio; no
    interpolation / reference-image / extension features (Veo-only).
    Seedance (BytePlus ModelArk, REST): first-frame + first+last-frame interpolation
    + silent video (generate_audio=false). NOTE: the 2.0 series REJECTS direct upload
    of images with real human FACES — so for our face-based clone keyframes use
    Seedance 1.5 Pro (silent + interpolation, NOT face-restricted) as the default.
    """

    # Veo (Google)
    VEO_3_1      = "veo-3.1-generate-preview"
    VEO_3_1_FAST = "veo-3.1-fast-generate-preview"
    VEO_3_1_LITE = "veo-3.1-lite-generate-preview"

    # Grok (xAI Imagine) — only 1.5 is supported
    GROK_IMAGINE_VIDEO_1_5 = "grok-imagine-video-1.5"

    # Seedance (BytePlus ModelArk). All ids verified against account 3002778785:
    # the 2.0 series (dreamina-prefixed) is activated + working; 1.5 Pro is a valid
    # id but needs activating in the Ark Console. 1.5 Pro = silent + first+last
    # interpolation and (unlike 2.0) NOT face-restricted → the right default for our
    # face-based clone keyframes. The 2.0 series rejects real-face image uploads.
    SEEDANCE_1_5_PRO = "seedance-1-5-pro-251215"        # needs activation; face-safe
    SEEDANCE_2_0 = "dreamina-seedance-2-0-260128"       # activated; face-restricted
    SEEDANCE_2_0_FAST = "dreamina-seedance-2-0-fast-260128"
    SEEDANCE_2_0_MINI = "dreamina-seedance-2-0-mini-260615"


# Veo 3.1: referenceImages + interpolation — the right default for our keyframe
# → clip flow. Analysis is cached per clone so quality > marginal cost.
DEFAULT_VIDEO_GEN_MODEL = VideoModel.VEO_3_1


class VideoProvider(str, Enum):
    """Which backend serves a VideoModel — drives client + key selection."""

    VEO      = "veo"       # Google, google-genai SDK
    GROK     = "grok"      # xAI Imagine, SDK
    SEEDANCE = "seedance"  # BytePlus ModelArk, REST


def video_provider_for(model: str | None) -> VideoProvider:
    """Resolve a video model id to its provider (defaults to Veo)."""
    m = str(model or "").lower()
    if m.startswith("grok"):
        return VideoProvider.GROK
    if "seedance" in m:          # e.g. dreamina-seedance-2-0-...
        return VideoProvider.SEEDANCE
    return VideoProvider.VEO


class VideoUnderstandingModel(str, Enum):
    """Gemini models that support video understanding — "Gemini 2.5 and later"
    (ai.google.dev/gemini-api/docs/video-understanding).

    Deprecations (ai.google.dev/gemini-api/docs/deprecations): gemini-3-pro-preview
    was RETIRED 2026-03-09; gemini-2.5-* deprecate 2026-10-16. So the current
    pro/flash are the 3.x generation, with gemini-2.5-pro kept as a still-live
    fallback (the model the clone analysis was empirically validated on).
    """

    GEMINI_3_1_PRO   = "gemini-3.1-pro-preview"   # current pro — deepest reasoning over video
    GEMINI_3_5_FLASH = "gemini-3.5-flash"          # current flash — cheaper; the doc's example model
    GEMINI_2_5_PRO   = "gemini-2.5-pro"            # legacy pro, live until 2026-10-16


# 3.1-pro is the default — the current live pro (replaces the retired 3-pro-preview
# and the deprecating 2.5-pro). The analysis is cached per clone (paid once), so
# quality (catching the transformation + on-screen text) > marginal cost.
DEFAULT_VIDEO_UNDERSTANDING_MODEL = VideoUnderstandingModel.GEMINI_3_1_PRO


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
    Provider.ANTHROPIC: ModelName.CLAUDE_SONNET_4_6,
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
