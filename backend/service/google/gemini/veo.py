"""Veo on the Gemini API: submit, poll, download.

``generate_videos`` returns a long-running operation, not a clip. Google quotes
11 seconds to 6 minutes at peak, so the client polls every ``poll_seconds``
until the operation is done or ``deadline_seconds`` pass, then downloads the
file straight away: the Gemini API keeps a generated video for two days, and
Duct's copy in project storage is the one that lasts.

What the June prototype learned the hard way, kept here so nobody relearns it:

* ``generate_audio`` fails every call on the Gemini API ("only supported in …
  Vertex") — Veo 3.x always has sound there, so the flag is never sent.
* A first frame (``image``) and ``reference_images`` together are a 400, which
  is one reason v1 takes frames and no references.
* ``number_of_videos`` is not in Veo 3.1's parameter table; the default is one.

A filtered clip is not an exception on Google's side: the operation finishes
with no videos and a list of reasons. That becomes ``SAFETY`` with the reasons
attached, because "try again" is the wrong answer to it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from service.videos.client import VideoAPIError, VideoErrorCode
from service.videos.schema import GeneratedVideo, GenerateVideoRequest, VideoFrame

logger = logging.getLogger(__name__)

POLL_SECONDS = 10.0
# Google's own worst case is six minutes; ten leaves room for a slow download.
DEADLINE_SECONDS = 600.0

_SAFETY_WORDS = ("safety", "responsible ai", "violat", "policy", "blocked", "filtered", "sensitive")


class GeminiVeoError(VideoAPIError):
    label = "Veo"


def _code_for(status: int | None, message: str) -> VideoErrorCode:
    text = (message or "").lower()
    if any(word in text for word in _SAFETY_WORDS):
        return VideoErrorCode.SAFETY
    if status in (401, 403):
        return VideoErrorCode.AUTH
    if status == 402:
        return VideoErrorCode.BILLING
    if status is not None and 400 <= status < 500 and status != 429:
        return VideoErrorCode.INVALID
    return VideoErrorCode.PROVIDER


def _image(frame: VideoFrame) -> Any:
    from google.genai import types

    return types.Image(image_bytes=frame.data, mime_type=frame.mime_type)


class GeminiVeoClient:
    """One instance per clip. ``client`` and ``sleep`` exist for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        client: Any = None,
        poll_seconds: float = POLL_SECONDS,
        deadline_seconds: float = DEADLINE_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("GeminiVeoClient: api_key is required")
            from google import genai

            client = genai.Client(api_key=api_key)
        self._aio = client.aio
        self._poll_seconds = poll_seconds
        self._deadline_seconds = deadline_seconds
        self._sleep = sleep

    async def generate_video(
        self,
        request: GenerateVideoRequest,
        *,
        first_frame: VideoFrame | None = None,
        last_frame: VideoFrame | None = None,
    ) -> GeneratedVideo:
        from google.genai import errors, types

        model = request.model.value
        config = types.GenerateVideosConfig(
            aspect_ratio=request.aspect_ratio.value,
            duration_seconds=request.duration_seconds,
            resolution=request.resolution.value,
            negative_prompt=request.negative_prompt or None,
            last_frame=_image(last_frame) if last_frame is not None else None,
        )
        try:
            operation = await self._aio.models.generate_videos(
                model=model,
                prompt=request.prompt,
                image=_image(first_frame) if first_frame is not None else None,
                config=config,
            )
            waited = 0.0
            while not operation.done:
                if waited >= self._deadline_seconds:
                    raise GeminiVeoError(
                        f"no clip after {int(waited)} s", model=model, code=VideoErrorCode.TIMEOUT
                    )
                await self._sleep(self._poll_seconds)
                waited += self._poll_seconds
                operation = await self._aio.operations.get(operation)
        except errors.APIError as exc:
            raise GeminiVeoError(
                exc.message or str(exc), model=model, code=_code_for(exc.code, exc.message or ""),
                http_status=exc.code,
            ) from exc

        if operation.error:
            message = str((operation.error or {}).get("message") or operation.error)
            raise GeminiVeoError(message, model=model, code=_code_for(None, message))

        response = operation.response or operation.result
        videos = list(getattr(response, "generated_videos", None) or [])
        if not videos:
            reasons = [str(r) for r in (getattr(response, "rai_media_filtered_reasons", None) or [])]
            filtered = bool(reasons) or bool(getattr(response, "rai_media_filtered_count", 0))
            raise GeminiVeoError(
                "; ".join(reasons) or "no video returned",
                model=model,
                code=VideoErrorCode.SAFETY if filtered else VideoErrorCode.PROVIDER,
            )

        video = videos[0].video
        try:
            data = await self._aio.files.download(file=video)
        except errors.APIError as exc:
            raise GeminiVeoError(
                f"download failed: {exc.message or exc}", model=model, http_status=exc.code
            ) from exc
        data = data or getattr(video, "video_bytes", None)
        if not data:
            raise GeminiVeoError("the finished clip had no bytes", model=model)
        return GeneratedVideo(data=data, mime_type=getattr(video, "mime_type", None) or "video/mp4")
