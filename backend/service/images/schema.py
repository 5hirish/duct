"""Pydantic request/response models shared by every image backend.

One request shape for Gemini, OpenAI and xAI: the content tools build a
``GenerateImageRequest`` / ``EditImageRequest`` once and hand it to whichever
client the run resolved (see ``service/images/client.py``). Each client maps
the provider-neutral fields — aspect ratio, size, count — onto its own wire
format, and prunes what its model cannot take (e.g. GEMINI_3_1_FLASH_IMAGE
collapses LOW/MEDIUM → MINIMAL/HIGH thinking levels; OpenAI wants a pixel
size, not a ratio). ``service/images/sizing.py`` holds those translations.

Every flag is an enum — no bare strings.

Some fields here are inert since Imagen was retired: negative_prompt, seed and
person_generation on generate, and edit_mode / mask / style / subject refs on
edit, were all Imagen-only options. They are kept — the @tool surface and
stored params still carry them — but no current backend honours them.
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


class PersonGeneration(StrEnum):
    ALLOW_ALL    = "allow_all"
    ALLOW_ADULT  = "allow_adult"
    DONT_ALLOW   = "dont_allow"


class ThinkingLevel(StrEnum):
    MINIMAL = "minimal"
    LOW     = "low"
    MEDIUM  = "medium"
    HIGH    = "high"


class EditMode(StrEnum):
    INPAINT_INSERT      = "inpaint_insert"
    INPAINT_REMOVAL     = "inpaint_removal"
    OUTPAINT            = "outpaint"
    BGSWAP              = "bgswap"
    PRODUCT_IMAGE       = "product_image"
    STYLE_TRANSFER      = "style_transfer"


class MaskMode(StrEnum):
    USER_PROVIDED = "user_provided"
    BACKGROUND    = "background"
    FOREGROUND    = "foreground"
    SEMANTIC      = "semantic"


class SubjectType(StrEnum):
    PERSON  = "person"
    ANIMAL  = "animal"
    PRODUCT = "product"
    DEFAULT = "default"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class GenerateImageRequest(BaseModel):
    """Inputs for ``ImageClient.generate_image()`` on any backend."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    model:  ImageModel = DEFAULT_IMAGE_MODEL

    # Single-reference legacy field — kept for backward compatibility. Use
    # input_asset_ids (below) for the dual-reference pattern (character +
    # camera/style).
    input_image_url:   HttpUrl | None = None

    # Multiple reference assets. Bytes are resolved by the @tool layer and
    # passed in order: Gemini takes them as inline parts, OpenAI as the
    # ``image`` list of an edits call, xAI takes the first only (its edits
    # endpoint is single-image). Max 3 recommended in practice; the Gemini
    # 3.x spec accepts up to 14 (10 object + 4 character) but passing >3
    # routinely is a code smell.
    #
    # Common pattern: [character_ref, camera_ref] for slides 2-5 — the
    # first locks face/skin/hair, the second imitates TikTok framing.
    # When this list has 2+ entries the agent's @tool wrapper prepends
    # a role-explanation prefix to the prompt; see service/google/gemini/client.
    input_asset_ids:   list[UUID] = Field(default_factory=list)

    aspect_ratio:      AspectRatio = AspectRatio.PORTRAIT_9_16
    # 2K so a 9:16 render (~1152×2048) covers the 1080×1920 TikTok slide without
    # upscaling; 1K (~768×1376) was soft on the long edge.
    image_size:        ImageSize   = ImageSize.K2
    number_of_images:  int = Field(default=1, ge=1, le=8)
    seed:              int | None = None
    negative_prompt:   str | None = None
    person_generation: PersonGeneration | None = None
    include_text:      bool = False
    thinking_level:    ThinkingLevel | None = None
    output_mime_type:  Literal["image/png", "image/jpeg"] = "image/png"


class EditImageRequest(BaseModel):
    """Inputs for ``ImageClient.edit_image()`` on any backend."""

    model_config = ConfigDict(extra="forbid")

    prompt:          str = Field(min_length=1)
    input_asset_id:  UUID
    model:           ImageModel = DEFAULT_IMAGE_MODEL

    edit_mode:       EditMode | None = None
    mask_asset_id:   UUID | None = None
    mask_mode:       MaskMode | None = None
    style_asset_id:  UUID | None = None
    subject_asset_id: UUID | None = None
    subject_type:    SubjectType | None = None

    aspect_ratio:    AspectRatio | None = None
    number_of_images: int = Field(default=1, ge=1, le=8)
    seed:            int | None = None
    negative_prompt: str | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class GeneratedImage(BaseModel):
    """One image returned by a backend. data is raw bytes (not base64)."""

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
