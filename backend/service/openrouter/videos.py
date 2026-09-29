"""OpenRouter video backend: Seedance, which no first-party key here reaches.

``POST /api/v1/videos`` starts a job and answers with its id; ``GET
/videos/{id}`` reports ``pending`` → ``in_progress`` → ``completed`` (or
``failed`` / ``cancelled`` / ``expired``); ``GET /videos/{id}/content`` is the
file. A completed job also carries ``usage.cost``, the amount OpenRouter billed
for it, which is why Seedance has no row in ``VIDEO_PRICE_PER_SECOND``: this
figure is exact where a per-second table would be an estimate (Seedance bills
by video token, which moves with resolution and length).

Raw httpx rather than the ``openrouter`` SDK, for the same reason as
``service/openrouter/images.py``: an injectable ``transport`` lets the offline
suite assert on the request that would have gone over the wire.

A frame goes as its public https URL when it has one (R2 in production) and as
a data URI otherwise: a clip made on a laptop has no address OpenRouter could
fetch. OpenRouter's docs show only URLs; the live test covers the data URI.

Seedance refuses a first frame that shows a realistic person ("may contain real
person"), stylised faces and people-free shots pass. Probed on BytePlus in
June; OpenRouter routes Seedance to the same upstream. That failure gets its
own code so the agent can say what to change instead of retrying.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from service.videos.client import VideoAPIError, VideoErrorCode
from service.videos.schema import GeneratedVideo, GenerateVideoRequest, VideoFrame

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
POLL_SECONDS = 10.0
DEADLINE_SECONDS = 600.0
# One request, not the job: a submit or a poll answers in seconds, and the
# download is one file of a few megabytes.
_REQUEST_TIMEOUT_SECONDS = 120.0

_DONE = "completed"
_FAILED = frozenset({"failed", "cancelled", "expired"})

_PERSON = re.compile(r"real person|real people|realistic (person|people|human|face)|human face", re.I)
_SAFETY = re.compile(r"moderat|safety|sensitive|polic|inappropriate|violat|blocked|not allowed", re.I)


class OpenRouterVideoError(VideoAPIError):
    label = "OpenRouter video"


def _code_for(status: int | None, message: str) -> VideoErrorCode:
    if _PERSON.search(message or ""):
        return VideoErrorCode.PERSON
    if _SAFETY.search(message or ""):
        return VideoErrorCode.SAFETY
    if status in (401, 403):
        return VideoErrorCode.AUTH
    if status == 402:
        return VideoErrorCode.BILLING
    if status is not None and 400 <= status < 500 and status != 429:
        return VideoErrorCode.INVALID
    return VideoErrorCode.PROVIDER


def _frame_url(frame: VideoFrame) -> str:
    if frame.url.startswith("https://"):
        return frame.url
    return f"data:{frame.mime_type};base64,{base64.b64encode(frame.data).decode('ascii')}"


def _message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or fallback)
        if error:
            return str(error)
    return fallback


class OpenRouterVideoClient:
    """One instance per clip. ``transport`` and ``sleep`` exist for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OPENROUTER_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        poll_seconds: float = POLL_SECONDS,
        deadline_seconds: float = DEADLINE_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouterVideoClient: api_key is required")
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
            transport=transport,
        )
        self._poll_seconds = poll_seconds
        self._deadline_seconds = deadline_seconds
        self._sleep = sleep

    @staticmethod
    def body(
        request: GenerateVideoRequest,
        *,
        first_frame: VideoFrame | None = None,
        last_frame: VideoFrame | None = None,
    ) -> dict[str, Any]:
        """The submit body. Public so a test can read it without a transport."""
        body: dict[str, Any] = {
            "model": request.model.value,
            "prompt": request.prompt,
            "duration": request.duration_seconds,
            "resolution": request.resolution.value,
            "aspect_ratio": request.aspect_ratio.value,
            # Priced the same with or without on both Seedance models, and a
            # clip with its own sound is one the user can post as it is.
            "generate_audio": True,
        }
        frames = [
            {"type": "image_url", "image_url": {"url": _frame_url(frame)}, "frame_type": kind}
            for frame, kind in ((first_frame, "first_frame"), (last_frame, "last_frame"))
            if frame is not None
        ]
        if frames:
            body["frame_images"] = frames
        return body

    async def generate_video(
        self,
        request: GenerateVideoRequest,
        *,
        first_frame: VideoFrame | None = None,
        last_frame: VideoFrame | None = None,
    ) -> GeneratedVideo:
        model = request.model.value
        try:
            job = await self._json("POST", "/videos", model, json=self.body(
                request, first_frame=first_frame, last_frame=last_frame,
            ))
            job_id = str(job.get("id") or "")
            if not job_id:
                raise OpenRouterVideoError("the submit answered with no job id", model=model)

            waited = 0.0
            while str(job.get("status") or "") != _DONE:
                status = str(job.get("status") or "")
                if status in _FAILED:
                    message = _message(job, f"the job ended {status}")
                    raise OpenRouterVideoError(message, model=model, code=_code_for(None, message))
                if waited >= self._deadline_seconds:
                    raise OpenRouterVideoError(
                        f"no clip after {int(waited)} s (job {job_id})",
                        model=model, code=VideoErrorCode.TIMEOUT,
                    )
                await self._sleep(self._poll_seconds)
                waited += self._poll_seconds
                job = await self._json("GET", f"/videos/{job_id}", model)

            usage = job.get("usage") if isinstance(job.get("usage"), dict) else {}
            cost = usage.get("cost")
            try:
                resp = await self._client.get(f"/videos/{job_id}/content", params={"index": 0})
            except httpx.HTTPError as exc:
                raise OpenRouterVideoError(f"download failed: {exc}", model=model) from exc
            if resp.status_code >= 400 or not resp.content:
                raise OpenRouterVideoError(
                    f"download failed: {resp.text[:300]}", model=model, http_status=resp.status_code
                )
            mime = (resp.headers.get("content-type") or "video/mp4").split(";")[0].strip()
            return GeneratedVideo(
                data=resp.content,
                mime_type=mime if mime.startswith("video/") else "video/mp4",
                cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
            )
        finally:
            await self._client.aclose()

    async def _json(self, method: str, path: str, model: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise OpenRouterVideoError(str(exc), model=model) from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code >= 400:
            message = _message(payload, resp.text[:500])
            raise OpenRouterVideoError(
                message, model=model, code=_code_for(resp.status_code, message),
                http_status=resp.status_code,
            )
        return payload if isinstance(payload, dict) else {}
