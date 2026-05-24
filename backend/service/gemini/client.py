"""Async wrapper around google-genai for image generation + editing.

Two methods:
  generate_image(request) — branches on model prefix: Imagen models use
                            client.models.generate_images; Gemini-class
                            models use client.models.generate_content with
                            an inline image attached when an input asset
                            is provided.

  edit_image(request, base_bytes, mask_bytes?, style_bytes?, subject_bytes?)
                          — Imagen models use client.models.edit_image with
                            RawReferenceImage + Mask/Style/Subject refs.
                            Gemini-class models do edit-style continuation
                            via generate_content with the base image inline.

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


_IMAGEN_PREFIX = "imagen-"


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
    ) -> list[GeneratedImage]:
        """Generate images from a text prompt.

        For Imagen models, image_size + person_generation + negative_prompt
        all apply. For Gemini-class models, image_size is ignored and
        input_bytes (if provided) is attached inline for edit-style flow.
        """
        if request.model.value.startswith(_IMAGEN_PREFIX):
            return await asyncio.to_thread(self._run_imagen_generate, request)
        return await asyncio.to_thread(
            self._run_gemini_generate,
            request,
            input_bytes,
        )

    async def edit_image(
        self,
        request: EditImageRequest,
        *,
        base_bytes: bytes,
        mask_bytes:    bytes | None = None,
        style_bytes:   bytes | None = None,
        subject_bytes: bytes | None = None,
    ) -> list[GeneratedImage]:
        """Edit an existing image. base_bytes is required (the input asset)."""
        if request.model.value.startswith(_IMAGEN_PREFIX):
            return await asyncio.to_thread(
                self._run_imagen_edit,
                request,
                base_bytes, mask_bytes, style_bytes, subject_bytes,
            )
        return await asyncio.to_thread(
            self._run_gemini_edit,
            request,
            base_bytes,
        )

    # ------------------------------------------------------------------
    # Imagen path — synchronous, run inside asyncio.to_thread
    # ------------------------------------------------------------------

    def _run_imagen_generate(self, request: GenerateImageRequest) -> list[GeneratedImage]:
        from google.genai import types

        cfg_kwargs: dict[str, Any] = {
            "number_of_images": request.number_of_images,
            "aspect_ratio":     request.aspect_ratio.value,
            "output_mime_type": request.output_mime_type,
        }
        # Fast variant doesn't accept image_size.
        if request.model != ImageModel.IMAGEN_4_FAST_GENERATE_001:
            cfg_kwargs["image_size"] = request.image_size.value
        if request.negative_prompt:
            cfg_kwargs["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            cfg_kwargs["seed"] = request.seed
        if request.person_generation is not None:
            cfg_kwargs["person_generation"] = request.person_generation.value

        try:
            resp = self._client.models.generate_images(
                model=request.model.value,
                prompt=request.prompt,
                config=types.GenerateImagesConfig(**cfg_kwargs),
            )
        except Exception as exc:
            raise GeminiAPIError(str(exc), model=request.model.value) from exc

        return _extract_imagen_images(resp, request.model.value)

    def _run_imagen_edit(
        self,
        request: EditImageRequest,
        base_bytes: bytes,
        mask_bytes:    bytes | None,
        style_bytes:   bytes | None,
        subject_bytes: bytes | None,
    ) -> list[GeneratedImage]:
        from google.genai import types

        reference_images: list[Any] = [
            types.RawReferenceImage(
                reference_id=0,
                reference_image=types.Image(image_bytes=base_bytes, mime_type="image/png"),
            )
        ]
        next_id = 1
        if mask_bytes is not None or request.mask_mode is not None:
            mask_image = (
                types.Image(image_bytes=mask_bytes, mime_type="image/png")
                if mask_bytes is not None else None
            )
            mask_cfg_kwargs: dict[str, Any] = {}
            if request.mask_mode is not None:
                mask_cfg_kwargs["mask_mode"] = request.mask_mode.value
            reference_images.append(
                types.MaskReferenceImage(
                    reference_id=next_id,
                    reference_image=mask_image,
                    config=types.MaskReferenceConfig(**mask_cfg_kwargs) if mask_cfg_kwargs else None,
                )
            )
            next_id += 1
        if style_bytes is not None:
            reference_images.append(
                types.StyleReferenceImage(
                    reference_id=next_id,
                    reference_image=types.Image(image_bytes=style_bytes, mime_type="image/png"),
                )
            )
            next_id += 1
        if subject_bytes is not None:
            sub_cfg = None
            if request.subject_type is not None:
                sub_cfg = types.SubjectReferenceConfig(subject_type=request.subject_type.value)
            reference_images.append(
                types.SubjectReferenceImage(
                    reference_id=next_id,
                    reference_image=types.Image(image_bytes=subject_bytes, mime_type="image/png"),
                    config=sub_cfg,
                )
            )
            next_id += 1

        cfg_kwargs: dict[str, Any] = {
            "number_of_images": request.number_of_images,
        }
        if request.edit_mode is not None:
            cfg_kwargs["edit_mode"] = request.edit_mode.value
        if request.aspect_ratio is not None:
            cfg_kwargs["aspect_ratio"] = request.aspect_ratio.value
        if request.seed is not None:
            cfg_kwargs["seed"] = request.seed
        if request.negative_prompt:
            cfg_kwargs["negative_prompt"] = request.negative_prompt

        try:
            resp = self._client.models.edit_image(
                model=request.model.value,
                prompt=request.prompt,
                reference_images=reference_images,
                config=types.EditImageConfig(**cfg_kwargs),
            )
        except Exception as exc:
            raise GeminiAPIError(str(exc), model=request.model.value) from exc

        return _extract_imagen_images(resp, request.model.value)

    # ------------------------------------------------------------------
    # Gemini-class path — generate_content with inline image support
    # ------------------------------------------------------------------

    def _run_gemini_generate(
        self,
        request: GenerateImageRequest,
        input_bytes: bytes | None,
    ) -> list[GeneratedImage]:
        from google.genai import types

        parts: list[Any] = [types.Part.from_text(text=request.prompt)]
        if input_bytes is not None:
            parts.insert(
                0,
                types.Part.from_bytes(data=input_bytes, mime_type="image/png"),
            )

        cfg_kwargs: dict[str, Any] = {
            "response_modalities": ["IMAGE", "TEXT"],
        }
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
        try:
            resp = self._client.models.generate_content(
                model=request.model.value,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )
        except Exception as exc:
            raise GeminiAPIError(str(exc), model=request.model.value) from exc

        return _extract_gemini_images(resp, request.model.value)


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _collapse_thinking_for_gemini_3_1(model: ImageModel, level):
    """gemini-3.1-flash-image only supports MINIMAL or HIGH; collapse others."""
    from service.gemini.schema import ThinkingLevel
    if model == ImageModel.GEMINI_3_1_FLASH_IMAGE_PREVIEW:
        if level in (ThinkingLevel.LOW, ThinkingLevel.MEDIUM):
            return ThinkingLevel.MINIMAL if level == ThinkingLevel.LOW else ThinkingLevel.HIGH
    return level


def _extract_imagen_images(resp: Any, model: str) -> list[GeneratedImage]:
    images = getattr(resp, "generated_images", None) or []
    out: list[GeneratedImage] = []
    for item in images:
        img = getattr(item, "image", None)
        if img is None:
            continue
        data = getattr(img, "image_bytes", None)
        if not data:
            continue
        mime = getattr(img, "mime_type", "image/png") or "image/png"
        out.append(GeneratedImage(data=data, mime_type=mime))
    if not out:
        raise GeminiAPIError("No images returned by Imagen response", model=model)
    return out


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
