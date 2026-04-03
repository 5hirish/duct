"""Provider and model enums with helper functions.

Follows the nomadtools agents/models.py pattern for provider-agnostic
model initialization via LangChain's init_chat_model().
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class Provider(str, Enum):
    OPENAI = "openai"
    GOOGLE_GENAI = "google_genai"
    ANTHROPIC = "anthropic"


class ModelName(str, Enum):
    # OpenAI
    GPT_5_MINI = "gpt-5-mini"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    # Google
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    # Anthropic
    CLAUDE_SONNET = "claude-sonnet-4-6"
    CLAUDE_HAIKU = "claude-haiku-4-5-20251001"


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


def resolve_provider(name: Optional[str]) -> Provider:
    """Resolve a string to a Provider enum, defaulting to GOOGLE_GENAI."""
    if not name:
        return Provider.GOOGLE_GENAI
    try:
        return Provider(name.lower().strip())
    except ValueError:
        return Provider.GOOGLE_GENAI


def resolve_model(name: Optional[str], provider: Provider) -> ModelName:
    """Resolve a string to a ModelName enum, defaulting per provider."""
    if not name:
        return DEFAULT_MODELS.get(provider, ModelName.GEMINI_2_5_FLASH)
    try:
        return ModelName(name.strip())
    except ValueError:
        return DEFAULT_MODELS.get(provider, ModelName.GEMINI_2_5_FLASH)
