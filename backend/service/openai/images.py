"""OpenAI image backend — gpt-image-2 over the Images API.

The Images API rather than the Responses ``image_generation`` tool: the tool
wraps every picture in a paid gpt-5.x chat turn and returns it as a content
block, which is the wrong shape for a service whose callers hand it bytes and
want bytes back. ``/images/generations`` and ``/images/edits`` are one call
each and the SDK Duct already depends on speaks them.

Reference images ride on the edits endpoint: OpenAI has no "generate with
references" call, an edit with several ``image`` inputs *is* that. Which
means a generate-with-refs and an edit are the same request here, differing
only in which image comes first.

Only gpt-image-2 is targeted. gpt-image-1.5, gpt-image-1-mini and
chatgpt-image-latest shut down on 2026-12-01 (announced 2026-06-02), and
gpt-image-2 processes every input at high fidelity on its own, so
``input_fidelity`` is deliberately never sent — the API rejects it there.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from service.images.client import ImageAPIError
from service.images.schema import (
    EditImageRequest,
    GenerateImageRequest,
    GeneratedImage,
    ImageSize,
)
from service.images.sizing import openai_size

logger = logging.getLogger(__name__)

_OUTPUT_FORMAT = "png"
_OUTPUT_MIME = "image/png"
# The API is generous with edit inputs (sixteen on gpt-image-1); the tool
# layer caps references at three long before this matters.
_FILE_TYPE = "image/png"


class OpenAIAPIError(ImageAPIError):
    label = "OpenAI"


def _file(data: bytes, name: str) -> tuple[str, bytes, str]:
    return (f"{name}.png", data, _FILE_TYPE)


class OpenAIImageClient:
    """One instance per request; the async SDK client is cheap to build."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OpenAIImageClient: api_key is required")
        from openai import AsyncOpenAI  # late import — heavy module

        self._client = AsyncOpenAI(api_key=api_key)

    async def generate_image(
        self,
        request: GenerateImageRequest,
        *,
        input_bytes: bytes | None = None,
        input_bytes_list: list[bytes] | None = None,
    ) -> list[GeneratedImage]:
        refs = list(input_bytes_list) if input_bytes_list else (
            [input_bytes] if input_bytes is not None else []
        )
        params: dict[str, Any] = {
            "model": request.model.value,
            "prompt": request.prompt,
            "n": request.number_of_images,
            "size": openai_size(request.aspect_ratio, request.image_size),
            "output_format": _OUTPUT_FORMAT,
        }
        try:
            if refs:
                resp = await self._client.images.edit(
                    image=[_file(b, f"ref-{i}") for i, b in enumerate(refs)], **params
                )
            else:
                resp = await self._client.images.generate(**params)
        except Exception as exc:
            raise OpenAIAPIError(
                str(exc), model=request.model.value,
                http_status=getattr(exc, "status_code", None),
            ) from exc
        return _extract(resp, request.model.value)

    async def edit_image(
        self,
        request: EditImageRequest,
        *,
        base_bytes: bytes,
        mask_bytes: bytes | None = None,
        style_bytes: bytes | None = None,
        subject_bytes: bytes | None = None,
    ) -> list[GeneratedImage]:
        # The base image leads; style and subject references follow as further
        # inputs, which is how the edits endpoint takes "keep this look" hints.
        images = [_file(base_bytes, "base")]
        for name, extra in (("style", style_bytes), ("subject", subject_bytes)):
            if extra is not None:
                images.append(_file(extra, name))
        params: dict[str, Any] = {
            "model": request.model.value,
            "prompt": request.prompt,
            "n": request.number_of_images,
            "output_format": _OUTPUT_FORMAT,
            # An edit keeps the source dimensions unless a ratio was asked for.
            "size": (
                openai_size(request.aspect_ratio, ImageSize.K2)
                if request.aspect_ratio is not None else "auto"
            ),
        }
        if mask_bytes is not None:
            params["mask"] = _file(mask_bytes, "mask")
        try:
            resp = await self._client.images.edit(image=images, **params)
        except Exception as exc:
            raise OpenAIAPIError(
                str(exc), model=request.model.value,
                http_status=getattr(exc, "status_code", None),
            ) from exc
        return _extract(resp, request.model.value)


def _extract(resp: Any, model: str) -> list[GeneratedImage]:
    out: list[GeneratedImage] = []
    for item in getattr(resp, "data", None) or []:
        b64 = getattr(item, "b64_json", None)
        if b64:
            out.append(GeneratedImage(data=base64.b64decode(b64), mime_type=_OUTPUT_MIME))
    if not out:
        raise OpenAIAPIError("No images returned", model=model)
    return out
