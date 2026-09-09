"""Image generation and editing across providers.

Three backends behind one interface — Gemini (``service/google/gemini``),
OpenAI (``service/openai/images``) and xAI (``service/xai/images``) — chosen
per run by ``agents.engines.resolve_image_run`` from the keys the user
brought. The request/response models, the persistence helper and the size
translations live here because none of them belongs to one provider.

Outputs are persisted to the configured object store under
projects/{project_id}/generated/ and recorded as ContentAsset rows. The
agent's @tool wrappers return both the inline image (so a vision-capable
model can see the layout) and the stable public URL (so slides_html can
reference it).
"""

from service.images.client import ImageAPIError, ImageClient, image_client_for
from service.images.schema import (
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
from service.images.storage import asset_source_for, persist_generated_image

__all__ = [
    "EditImageRequest",
    "EditMode",
    "GenerateImageRequest",
    "GeneratedImage",
    "ImageAPIError",
    "ImageAsset",
    "ImageClient",
    "ImageSize",
    "MaskMode",
    "PersonGeneration",
    "SubjectType",
    "ThinkingLevel",
    "asset_source_for",
    "image_client_for",
    "persist_generated_image",
]
