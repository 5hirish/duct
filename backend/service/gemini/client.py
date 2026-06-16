"""Async wrapper around google-genai for image generation + editing.

Two methods:
  generate_image(request) — client.models.generate_content with any inline
                            reference images attached before the prompt.

  edit_image(request, base_bytes) — edit-style continuation via
                            generate_content with the base image inline.

The route / @tool layer reads input asset bytes from disk and passes them
in, so the client stays pure (no DB/filesystem coupling).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agents.models import ImageModel
from service.gemini.schema import (
    EditImageRequest,
    GenerateImageRequest,
    GeneratedImage,
)

logger = logging.getLogger(__name__)


class GeminiAPIError(RuntimeError):
    """Raised on any Gemini SDK failure. Carries model + http_status when known."""

    def __init__(self, message: str, *, model: str, http_status: int | None = None):
        self.model       = model
        self.http_status = http_status
        super().__init__(f"Gemini ({model}): {message}")


class GeminiImageClient:
    """Wraps google-genai. One instance per request is fine — the SDK's
    client is thread-safe but we don't reuse it across event loops.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("GeminiImageClient: api_key is required")
        from google import genai  # late import — heavy module
        self._client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_image(
        self,
        request: GenerateImageRequest,
        *,
        input_bytes: bytes | None = None,
        input_bytes_list: list[bytes] | None = None,
    ) -> list[GeneratedImage]:
        """Generate images from a text prompt.

        Any reference image bytes are attached inline as parts before the
        prompt.

        Reference passing:
          - `input_bytes_list` (preferred): N reference images passed in
            order. The first is treated as the character/subject reference;
            subsequent images are camera/style/layout references. When
            len >= 2, the caller should also pass a contextual prefix in
            `request.prompt` describing each image's role — see the
            content agent's generate_image @tool which does this
            automatically.
          - `input_bytes` (legacy): single reference, equivalent to a
            one-element `input_bytes_list`.
        """
        # Normalise to a single list. input_bytes_list wins if provided.
        bytes_list = (
            list(input_bytes_list)
            if input_bytes_list
            else ([input_bytes] if input_bytes is not None else [])
        )
        return await asyncio.to_thread(
            self._run_gemini_generate,
            request,
            bytes_list,
        )

    async def edit_image(
        self,
        request: EditImageRequest,
        *,
        base_bytes: bytes,
    ) -> list[GeneratedImage]:
        """Edit an existing image. base_bytes is required (the input asset)."""
        return await asyncio.to_thread(
            self._run_gemini_edit,
            request,
            base_bytes,
        )

    # ------------------------------------------------------------------
    # generate_content with inline image support
    # ------------------------------------------------------------------

    def _run_gemini_generate(
        self,
        request: GenerateImageRequest,
        input_bytes_list: list[bytes],
    ) -> list[GeneratedImage]:
        from google.genai import types

        # Order: reference images first, then text. Gemini reads parts
        # in order; the prompt should explicitly describe what each
        # preceding image is for. The agent's @tool wrapper handles this
        # via the contextual-prefix helper.
        image_parts = [
            types.Part.from_bytes(data=b, mime_type="image/png")
            for b in input_bytes_list
        ]
        parts: list[Any] = [*image_parts, types.Part.from_text(text=request.prompt)]

        cfg_kwargs: dict[str, Any] = {
            "response_modalities": ["IMAGE", "TEXT"],
        }
        # aspect_ratio + image_size ride in image_config for Gemini image models
        # (previously dropped — images defaulted to square and got cropped).
        img_cfg = _gemini_image_config(request)
        if img_cfg is not None:
            cfg_kwargs["image_config"] = img_cfg
        if request.thinking_level is not None:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=_collapse_thinking_for_gemini_3_1(
                    request.model, request.thinking_level
                ).value
            )

        try:
            resp = self._client.models.generate_content(
                model=request.model.value,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
        except Exception as exc:
            raise GeminiAPIError(str(exc), model=request.model.value) from exc

        return _extract_gemini_images(resp, request.model.value)

    def _run_gemini_edit(
        self,
        request: EditImageRequest,
        base_bytes: bytes,
    ) -> list[GeneratedImage]:
        from google.genai import types

        parts = [
            types.Part.from_bytes(data=base_bytes, mime_type="image/png"),
            types.Part.from_text(text=request.prompt),
        ]
        cfg_kwargs: dict[str, Any] = {"response_modalities": ["IMAGE", "TEXT"]}
        # Only set image_config if an aspect_ratio override was requested — an
        # edit otherwise keeps the source image's dimensions.
        img_cfg = _gemini_image_config(request)
        if img_cfg is not None:
            cfg_kwargs["image_config"] = img_cfg
        try:
            resp = self._client.models.generate_content(
                model=request.model.value,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
        except Exception as exc:
            raise GeminiAPIError(str(exc), model=request.model.value) from exc

        return _extract_gemini_images(resp, request.model.value)


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _gemini_image_config(request: Any):
    """Build a ``types.ImageConfig`` for the Gemini image path.

    Gemini image models read aspect_ratio + image_size from
    ``GenerateContentConfig.image_config`` (NOT top-level kwargs and NOT a
    negative_prompt — negative prompting isn't a concept for these models; see
    ai.google.dev/gemini-api/docs/image-generation). Returns None when neither
    is set (e.g. an edit that should keep the source dimensions).
    """
    from google.genai import types

    kw: dict[str, Any] = {}
    ar = getattr(request, "aspect_ratio", None)
    if ar is not None:
        kw["aspect_ratio"] = ar.value
    sz = getattr(request, "image_size", None)
    if sz is not None:
        kw["image_size"] = sz.value
    return types.ImageConfig(**kw) if kw else None


def _collapse_thinking_for_gemini_3_1(model: ImageModel, level):
    """gemini-3.1-flash-image only supports MINIMAL or HIGH; collapse others."""
    from service.gemini.schema import ThinkingLevel
    if model == ImageModel.GEMINI_3_1_FLASH_IMAGE:
        if level in (ThinkingLevel.LOW, ThinkingLevel.MEDIUM):
            return ThinkingLevel.MINIMAL if level == ThinkingLevel.LOW else ThinkingLevel.HIGH
    return level


# Role hint prepended to multi-reference Gemini-class calls. Without it,
# the model treats all images as equal context and may drift on either
# character identity or style/framing. Order matters — first image is
# always the character ref; subsequent images are style/layout.
#
# Sourced from the nomadapps tiktok-gen skill's `input_image_paths`
# guidance for slides 2-5 (character + camera/style reference combined).
_MULTI_REF_PREFIX_2 = (
    "The first image is the character reference — maintain her facial "
    "features, skin tone, hair colour and texture exactly. The second "
    "image is the framing/style reference — imitate its TikTok camera "
    "aesthetic, phone-held angle, film grain, and overall lighting quality."
)
_MULTI_REF_PREFIX_3 = (
    "The first image is the character reference — maintain her facial "
    "features, skin tone, hair colour and texture exactly. The second "
    "image is the framing/style reference — imitate its TikTok camera "
    "aesthetic, phone-held angle, film grain, and overall lighting quality. "
    "The third image is a supplementary reference — its role is described "
    "below in the prompt."
)


def build_multi_reference_prefix(num_references: int) -> str:
    """Return the role-explanation prefix the agent should prepend to its
    image prompt when passing 2+ reference images to a Gemini-class
    model. Returns an empty string for 0 or 1 references.

    Callers concatenate this with their own prompt:
        prompt = build_multi_reference_prefix(2) + "\\n\\n" + user_prompt
    """
    if num_references >= 3:
        return _MULTI_REF_PREFIX_3
    if num_references == 2:
        return _MULTI_REF_PREFIX_2
    return ""


def _extract_gemini_images(resp: Any, model: str) -> list[GeneratedImage]:
    out: list[GeneratedImage] = []
    candidates = getattr(resp, "candidates", []) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if content is None:
            continue
        for part in getattr(content, "parts", []) or []:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            mime = getattr(inline, "mime_type", "image/png") or "image/png"
            if data:
                out.append(GeneratedImage(data=data, mime_type=mime))
    if not out:
        raise GeminiAPIError("No images returned by Gemini response", model=model)
    return out
