"""Pydantic request/response models for the Gemini image service.

Every flag is an enum — no bare strings. Per-model option pruning happens
inside the client (e.g. GEMINI_3_1 collapses LOW/MEDIUM → MINIMAL/HIGH
thinking levels).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from agents.models import DEFAULT_IMAGE_MODEL, AspectRatio, ImageModel


class ImageSize(StrEnum):
    K1 = "1K"
    K2 = "2K"
    K4 = "4K"


class ThinkingLevel(StrEnum):
    MINIMAL = "minimal"
    LOW     = "low"
    MEDIUM  = "medium"
    HIGH    = "high"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class GenerateImageRequest(BaseModel):
    """Inputs for GeminiImageClient.generate_image()."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    model:  ImageModel = DEFAULT_IMAGE_MODEL

    # Single-reference legacy field — kept for backward compatibility. Use
    # input_asset_ids (below) for the dual-reference pattern (character +
    # camera/style).
    input_image_url:   HttpUrl | None = None

    # Multiple reference assets. Bytes are
    # resolved by the @tool layer and passed in order to the SDK as
    # separate inline_data parts. Max 3 recommended in practice; the
    # Gemini 3.x spec accepts up to 14 (10 object + 4 character) but
    # passing >3 routinely is a code smell.
    #
    # Common pattern: [character_ref, camera_ref] for slides 2-5 — the
    # first locks face/skin/hair, the second imitates TikTok framing.
    # When this list has 2+ entries the agent's @tool wrapper prepends
    # a role-explanation prefix to the prompt; see service/gemini/client.
    input_asset_ids:   list[UUID] = Field(default_factory=list)

    aspect_ratio:      AspectRatio = AspectRatio.PORTRAIT_9_16
    # 2K so a 9:16 render (~1152×2048) covers the 1080×1920 TikTok slide without
    # upscaling; 1K (~768×1376) was soft on the long edge.
    image_size:        ImageSize   = ImageSize.K2
    number_of_images:  int = Field(default=1, ge=1, le=8)
    seed:              int | None = None
    include_text:      bool = False
    thinking_level:    ThinkingLevel | None = None
    output_mime_type:  Literal["image/png", "image/jpeg"] = "image/png"


class EditImageRequest(BaseModel):
    """Inputs for GeminiImageClient.edit_image().

    Gemini-class edits are free-form generate_content continuations from the
    base image + prompt. (The structured mask / inpaint / style / subject
    reference flow was Imagen-only and was removed with the Imagen 4 endpoints.)
    """

    model_config = ConfigDict(extra="forbid")

    prompt:          str = Field(min_length=1)
    input_asset_id:  UUID
    model:           ImageModel = DEFAULT_IMAGE_MODEL

    aspect_ratio:    AspectRatio | None = None
    number_of_images: int = Field(default=1, ge=1, le=8)
    seed:            int | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class GeneratedImage(BaseModel):
    """One image returned by the Gemini SDK. data is raw bytes (not base64)."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    data:      bytes
    mime_type: str = "image/png"


class ImageAsset(BaseModel):
    """One persisted asset row — what the @tool wrapper returns to the agent."""

    model_config = ConfigDict(extra="forbid")

    asset_id:  UUID
    url:       str            # public URL into /uploads/...
    mime_type: str
    prompt:    str
    model:     str
    params:    dict
