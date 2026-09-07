"""Gemini services — image generation and grounded web search.

Two capabilities Duct supplies as its own tools, backed by Gemini, so a model
that lacks them natively still has them. See search.py for why search in
particular cannot be the provider built-in.

Wraps google-genai with typed Pydantic requests/responses. Outputs are
persisted to the Railway Volume at /app/uploads/projects/{project_id}/
generated/ and recorded as ContentAsset rows. The agent's @tool wrappers
return both the inline image (so the model can see the layout) and the
stable public URL (so slides_html can reference it).
"""

from service.google.gemini.client import GeminiAPIError, GeminiImageClient
from service.google.gemini.search import SEARCH_MODEL, search_web
from service.google.gemini.schema import (
    EditImageRequest,
    EditMode,
    GenerateImageRequest,
    GeneratedImage,
    ImageAsset,
    ImageSize,
    MaskMode,
    PersonGeneration,
    SubjectType,
    ThinkingLevel,
)
from service.google.gemini.storage import persist_generated_image

__all__ = [
    "EditImageRequest",
    "EditMode",
    "GeminiAPIError",
    "GeminiImageClient",
    "GenerateImageRequest",
    "GeneratedImage",
    "ImageAsset",
    "ImageSize",
    "MaskMode",
    "PersonGeneration",
    "SubjectType",
    "ThinkingLevel",
    "SEARCH_MODEL",
    "persist_generated_image",
    "search_web",
]
