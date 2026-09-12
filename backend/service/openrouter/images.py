"""OpenRouter image backend — the fourth implementation of one interface.

A gateway is a backend here for one reason: until it was, ``resolve_image_run``
walked ``IMAGE_PROVIDER_ORDER``, found no entry for OpenRouter, and returned
None — so a user whose only key was an OpenRouter one ran a whole content
session with every picture politely declined, and was told to go open an
account with Google, OpenAI or xAI. That is the exact complaint the image seam
was built to end.

``POST /api/v1/images`` rather than chat-completions with ``modalities``. The
dedicated endpoint speaks ``aspect_ratio`` + ``resolution`` + ``n`` +
``input_references``, which *is* ``GenerateImageRequest`` — no pixel arithmetic
as on OpenAI, no rung-mapping as on xAI. The chat shape would wrap each picture
in a paid chat turn and hand back a content block, the same reason
service/openai/images.py avoids OpenAI's Responses tool.

**The per-model table is the price of a gateway, and it is charged here.** The
four models disagree about everything a request carries: Flux takes no
``resolution``, Seedream stops at 2K, Recraft's ratio list omits 21:9 while
Gemini's omits 9:21, and three of the four cap ``n`` at 1 while the tool layer
offers up to 4. A first-party backend can hardcode one vendor's rules; this one
cannot, so ``_CAPS`` states them per model and every request is clamped to them
rather than sent hopefully. Values come from OpenRouter's own typed capability
table (``/api/v1/images/models``), which is the thing to re-read when adding a
row — not the model's marketing page.

Clamping rather than raising is the deliberate half. A slide run that asked for
four images and got one has a deliverable; one that got a 400 has nothing, and
the agent cannot tell the difference between "this model is single-image" and
"your key is bad". Every clamp logs what it changed.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from agents.models import ImageModel
from service.images.client import ImageAPIError
from service.images.schema import EditImageRequest, GenerateImageRequest, GeneratedImage
from service.images.sizing import nearest_aspect_ratio, openrouter_resolution

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_IMAGES = "/images"
# Image calls are slow by chat standards, and a gateway adds a hop to a queue
# that is already minutes long at 4K. Matches the xAI backend.
_TIMEOUT_SECONDS = 180.0
_INPUT_MIME = "image/png"
# What a response means when it names no media type. Only a fallback: Recraft
# answers ``image/svg+xml`` and that is the whole reason it is on the list, so
# the returned type is honoured rather than assumed.
_DEFAULT_OUTPUT_MIME = "image/png"


@dataclass(frozen=True)
class _Caps:
    """What one model will actually accept. Mirrors OpenRouter's own table.

    ``resolutions`` empty means the model takes no ``resolution`` field at all,
    which is different from "takes it and ignores it" — sending one is a 400.
    """

    aspect_ratios: tuple[str, ...]
    resolutions: tuple[str, ...]
    max_images: int
    max_references: int
    seed: bool


# "auto" is in several of these lists upstream and in none of them here: it is
# a routing instruction, not a ratio, and nearest_aspect_ratio would have to
# parse it as one. A brief always names a frame, so there is nothing to defer.
_CAPS: dict[ImageModel, _Caps] = {
    ImageModel.OR_GEMINI_3_1_FLASH_IMAGE: _Caps(
        aspect_ratios=(
            "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3",
            "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
        ),
        resolutions=("512", "1K", "2K", "4K"),
        max_images=1,
        max_references=14,
        seed=False,
    ),
    ImageModel.OR_SEEDREAM_5_PRO: _Caps(
        aspect_ratios=(
            "1:1", "1:2", "2:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
            "9:16", "16:9", "9:19.5", "19.5:9", "9:20", "20:9", "9:21", "21:9",
        ),
        resolutions=("1K", "2K"),
        max_images=1,
        max_references=14,
        seed=True,
    ),
    ImageModel.OR_FLUX_2_PRO: _Caps(
        aspect_ratios=("1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"),
        resolutions=(),
        max_images=1,
        max_references=8,
        seed=True,
    ),
    ImageModel.OR_RECRAFT_V4_VECTOR: _Caps(
        aspect_ratios=(
            "1:1", "2:1", "1:2", "3:2", "2:3", "4:3", "3:4",
            "5:4", "4:5", "16:9", "9:16",
        ),
        resolutions=(),
        max_images=6,
        max_references=10,
        seed=False,
    ),
}


class OpenRouterAPIError(ImageAPIError):
    label = "OpenRouter"


def _caps(model: ImageModel) -> _Caps:
    """The table row, or a refusal naming the omission.

    A model in the enum with no row would otherwise reach the wire with no
    clamping at all and fail as a vendor 400 — a confusing way to learn that
    half of an addition was made.
    """
    try:
        return _CAPS[model]
    except KeyError:
        raise OpenRouterAPIError(
            "no capability row — add one beside the ImageModel entry",
            model=model.value,
        ) from None


def _data_url(data: bytes) -> str:
    return f"data:{_INPUT_MIME};base64,{base64.b64encode(data).decode('ascii')}"


def _reference(data: bytes) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": _data_url(data)}}


def _clamp_images(wanted: int, caps: _Caps, model: str) -> int:
    if wanted <= caps.max_images:
        return wanted
    logger.warning(
        "openrouter %s: asked for %d images, model serves %d per call",
        model, wanted, caps.max_images,
    )
    return caps.max_images


def _clamp_references(refs: list[bytes], caps: _Caps, model: str) -> list[bytes]:
    if len(refs) <= caps.max_references:
        return refs
    logger.warning(
        "openrouter %s: dropping %d of %d references — model takes %d",
        model, len(refs) - caps.max_references, len(refs), caps.max_references,
    )
    return refs[: caps.max_references]


class OpenRouterImageClient:
    """One instance per request. ``transport`` exists for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OPENROUTER_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouterImageClient: api_key is required")
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def generate_image(
        self,
        request: GenerateImageRequest,
        *,
        input_bytes: bytes | None = None,
        input_bytes_list: list[bytes] | None = None,
    ) -> list[GeneratedImage]:
        model = request.model.value
        caps = _caps(request.model)
        refs = list(input_bytes_list) if input_bytes_list else (
            [input_bytes] if input_bytes is not None else []
        )
        body = self._body(
            model=model,
            prompt=request.prompt,
            caps=caps,
            number_of_images=request.number_of_images,
            aspect_ratio=nearest_aspect_ratio(request.aspect_ratio, caps.aspect_ratios),
            resolution=openrouter_resolution(request.image_size, caps.resolutions),
            seed=request.seed,
            references=_clamp_references(refs, caps, model),
        )
        return await self._post(body, model=model)

    async def edit_image(
        self,
        request: EditImageRequest,
        *,
        base_bytes: bytes,
        mask_bytes: bytes | None = None,
        style_bytes: bytes | None = None,
        subject_bytes: bytes | None = None,
    ) -> list[GeneratedImage]:
        """An edit is a generation whose first reference is the source image.

        There is no mask on this endpoint, so a mask is dropped and said out
        loud — the same answer the Gemini and xAI backends give, since masked
        editing retired with Imagen and nothing in the tool layer still asks
        for it.
        """
        model = request.model.value
        caps = _caps(request.model)
        if mask_bytes is not None:
            logger.warning(
                "openrouter %s edit_image: ignoring the mask — /images takes "
                "references and a prompt, not a masked region", model,
            )
        refs = [base_bytes]
        refs += [extra for extra in (style_bytes, subject_bytes) if extra is not None]
        body = self._body(
            model=model,
            prompt=request.prompt,
            caps=caps,
            number_of_images=request.number_of_images,
            # An edit keeps the source frame unless a ratio was asked for.
            aspect_ratio=(
                nearest_aspect_ratio(request.aspect_ratio, caps.aspect_ratios)
                if request.aspect_ratio is not None else None
            ),
            resolution=None,
            seed=request.seed,
            references=_clamp_references(refs, caps, model),
        )
        return await self._post(body, model=model)

    @staticmethod
    def _body(
        *,
        model: str,
        prompt: str,
        caps: _Caps,
        number_of_images: int,
        aspect_ratio: str | None,
        resolution: str | None,
        seed: int | None,
        references: list[bytes],
    ) -> dict[str, Any]:
        """Only the fields this model serves. An unsupported one is a 400."""
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": _clamp_images(number_of_images, caps, model),
        }
        if aspect_ratio is not None:
            body["aspect_ratio"] = aspect_ratio
        if resolution is not None:
            body["resolution"] = resolution
        if seed is not None and caps.seed:
            body["seed"] = seed
        if references:
            body["input_references"] = [_reference(data) for data in references]
        return body

    async def _post(self, body: dict[str, Any], *, model: str) -> list[GeneratedImage]:
        try:
            resp = await self._client.post(_IMAGES, json=body)
        except httpx.HTTPError as exc:
            raise OpenRouterAPIError(str(exc), model=model) from exc
        if resp.status_code >= 400:
            raise OpenRouterAPIError(resp.text[:500], model=model, http_status=resp.status_code)
        return _extract(resp.json(), model)


def _extract(payload: dict[str, Any], model: str) -> list[GeneratedImage]:
    """Base64 only — this endpoint returns bytes, never a URL to fetch.

    Which is why there is no equivalent of the xAI backend's result-URL
    download and its host check: there is no URL in the response to be careful
    about.
    """
    out: list[GeneratedImage] = []
    for item in payload.get("data") or []:
        b64 = item.get("b64_json")
        if b64:
            out.append(GeneratedImage(
                data=base64.b64decode(b64),
                mime_type=item.get("media_type") or _DEFAULT_OUTPUT_MIME,
            ))
    if not out:
        raise OpenRouterAPIError("No images returned", model=model)
    return out
