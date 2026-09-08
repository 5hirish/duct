"""xAI image backend — Grok Imagine over api.x.ai.

Plain httpx rather than the OpenAI SDK pointed at a base URL, because the
two APIs only look alike. Generation takes ``aspect_ratio`` + ``resolution``
where OpenAI takes ``size``, and rejects ``size`` outright; editing is a JSON
body carrying the source image as a data URL where OpenAI's is multipart.
Wrapping the OpenAI SDK would mean fighting its parameter validation on
every call, and there is nothing else to reuse.

Editing is single-image on this endpoint. A generate call with several
references therefore uses the first — the character reference, by the
tools' ordering convention — and logs what it dropped, the same way the
Gemini client reports the Imagen-only refs it cannot honour.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from service.images.client import ImageAPIError
from service.images.schema import EditImageRequest, GenerateImageRequest, GeneratedImage
from service.images.sizing import xai_aspect_ratio, xai_resolution

logger = logging.getLogger(__name__)

XAI_BASE_URL = "https://api.x.ai/v1"
_GENERATIONS = "/images/generations"
_EDITS = "/images/edits"
_RESPONSE_FORMAT = "b64_json"
_INPUT_MIME = "image/png"
# Image calls are slow by chat standards; a 2K render can take most of a minute.
_TIMEOUT_SECONDS = 180.0
# Where a result URL may point. The API's own host is api.x.ai; a URL answer
# is honoured only on xAI's domain, over TLS, and fetched with no credential —
# the bearer token is for api.x.ai and must not follow a URL the response body
# chose.
_RESULT_HOST_SUFFIX = ".x.ai"


class XAIAPIError(ImageAPIError):
    label = "xAI"


def _data_url(data: bytes) -> str:
    return f"data:{_INPUT_MIME};base64,{base64.b64encode(data).decode('ascii')}"


class XAIImageClient:
    """One instance per request. ``transport`` exists for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = XAI_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("XAIImageClient: api_key is required")
        self._transport = transport
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
        refs = list(input_bytes_list) if input_bytes_list else (
            [input_bytes] if input_bytes is not None else []
        )
        if refs:
            if len(refs) > 1:
                logger.warning(
                    "xai generate_image: using the first of %d references — "
                    "the edits endpoint takes one image", len(refs),
                )
            body = {
                "model": request.model.value,
                "prompt": request.prompt,
                "image": {"type": "image_url", "url": _data_url(refs[0])},
                "response_format": _RESPONSE_FORMAT,
            }
            return await self._post(_EDITS, body, model=request.model.value)
        body = {
            "model": request.model.value,
            "prompt": request.prompt,
            "n": request.number_of_images,
            "aspect_ratio": xai_aspect_ratio(request.aspect_ratio),
            "resolution": xai_resolution(request.image_size),
            "response_format": _RESPONSE_FORMAT,
        }
        return await self._post(_GENERATIONS, body, model=request.model.value)

    async def edit_image(
        self,
        request: EditImageRequest,
        *,
        base_bytes: bytes,
        mask_bytes: bytes | None = None,
        style_bytes: bytes | None = None,
        subject_bytes: bytes | None = None,
    ) -> list[GeneratedImage]:
        dropped = [
            name for name, data in (
                ("mask", mask_bytes), ("style", style_bytes), ("subject", subject_bytes),
            ) if data is not None
        ]
        if dropped:
            logger.warning(
                "xai edit_image: ignoring %s reference(s) — the edits endpoint "
                "takes the base image and prompt alone", "/".join(dropped),
            )
        body = {
            "model": request.model.value,
            "prompt": request.prompt,
            "image": {"type": "image_url", "url": _data_url(base_bytes)},
            "response_format": _RESPONSE_FORMAT,
        }
        return await self._post(_EDITS, body, model=request.model.value)

    async def _post(self, path: str, body: dict[str, Any], *, model: str) -> list[GeneratedImage]:
        try:
            resp = await self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise XAIAPIError(str(exc), model=model) from exc
        if resp.status_code >= 400:
            raise XAIAPIError(resp.text[:500], model=model, http_status=resp.status_code)
        return await self._extract(resp.json(), model)

    async def _extract(self, payload: dict[str, Any], model: str) -> list[GeneratedImage]:
        out: list[GeneratedImage] = []
        for item in payload.get("data") or []:
            b64 = item.get("b64_json")
            if b64:
                out.append(GeneratedImage(data=base64.b64decode(b64), mime_type=_INPUT_MIME))
                continue
            # The edits endpoint is documented against ``url`` only; honour a
            # URL answer rather than fail on the format we asked for.
            url = item.get("url")
            if url:
                image = await self._fetch_result(url, model=model)
                if image is not None:
                    out.append(image)
        if not out:
            raise XAIAPIError("No images returned", model=model)
        return out

    async def _fetch_result(self, url: str, *, model: str) -> GeneratedImage | None:
        """Download a result URL — anonymously, and only from xAI's own host.

        ``self._client`` carries the user's bearer token, and httpx sends a
        client's headers to any absolute URL it is handed. Following a URL from
        the response body with that client would hand the key to whatever host
        the body named. So the fetch goes through a bare client, and a URL off
        xAI's domain or off TLS is refused rather than fetched.
        """
        parsed = urlparse(url)
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme != "https" or not (host == _RESULT_HOST_SUFFIX[1:] or host.endswith(_RESULT_HOST_SUFFIX)):
            raise XAIAPIError(f"refusing result URL off xAI's domain: {url[:120]}", model=model)
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, transport=self._transport) as anon:
            fetched = await anon.get(url)
        if fetched.status_code >= 400 or not fetched.content:
            return None
        mime = fetched.headers.get("content-type", _INPUT_MIME).split(";")[0]
        return GeneratedImage(data=fetched.content, mime_type=mime or _INPUT_MIME)
