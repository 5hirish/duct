"""Seedance 2.0 (BytePlus ModelArk) image-to-video — a third video-gen provider
alongside Veo and Grok.

REST, via httpx (no SDK dependency, consistent with our other service clients):
submit ``POST /api/v3/contents/generations/tasks`` → poll
``GET /api/v3/contents/generations/tasks/{id}`` until ``status == "succeeded"`` →
download the result ``video_url`` → mp4 bytes. Mirrors the other video clients
(bytes in / bytes out).

Seedance 2.0 supports first-frame, first+last-frame (transformation), reference
images (1-9, mutually exclusive with first/last), native audio, and 4-15s clips.
Images are sent as base64 data URIs so it works in dev + prod alike.

NOTE: Seedance 2.0 REJECTS direct upload of reference images/videos containing
real human FACES (must be a trusted Seedance output / preset digital character /
authorized asset) — a Gemini-generated face keyframe may be rejected; confirm via
spike. UNVALIDATED end-to-end: response field names follow the docs and are parsed
defensively.
"""

from __future__ import annotations

import asyncio
import base64
import logging

from agents.models import VideoModel

logger = logging.getLogger(__name__)

# Single source of truth — the model id lives on the VideoModel enum.
DEFAULT_SEEDANCE_MODEL = VideoModel.SEEDANCE_2_0.value

_TASKS_URL = "https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks"
_SUBMIT_TIMEOUT_SECS = 60.0
_POLL_INTERVAL_SECS = 5.0
_MAX_WAIT_SECS = 10 * 60.0
_DOWNLOAD_TIMEOUT_SECS = 120.0

_DONE_STATES = {"succeeded", "success", "completed", "done"}
_FAIL_STATES = {"failed", "error", "expired", "canceled", "cancelled"}


class SeedanceVideoError(RuntimeError):
    """Raised on any Seedance failure (submit / poll / download)."""


class SeedanceVideoClient:
    """Wraps the BytePlus ModelArk Seedance video REST API. One instance per
    request is fine (mirrors GeminiVeoClient)."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("SeedanceVideoClient: api_key is required")
        self._key = api_key

    async def generate_video(
        self,
        *,
        prompt: str,
        first_frame: bytes | None = None,
        first_frame_mime: str = "image/png",
        last_frame: bytes | None = None,
        reference_images: list[bytes] | None = None,
        duration_seconds: int | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        generate_audio: bool = True,
        model: str = DEFAULT_SEEDANCE_MODEL,
    ) -> bytes:
        """Generate a clip and return its mp4 bytes. Image inputs map to the three
        mutually-exclusive Seedance scenarios: first+last (transformation) >
        first-only > reference images. Raises SeedanceVideoError on failure."""
        import httpx

        def _img(b: bytes, role: str) -> dict:
            uri = f"data:{first_frame_mime};base64,{base64.b64encode(b).decode('ascii')}"
            return {"type": "image_url", "image_url": {"url": uri}, "role": role}

        content: list[dict] = [{"type": "text", "text": prompt}]
        # first+last / first-only / reference are mutually exclusive (per the docs).
        if first_frame is not None and last_frame is not None:
            content.append(_img(first_frame, "first_frame"))
            content.append(_img(last_frame, "last_frame"))
        elif first_frame is not None:
            content.append(_img(first_frame, "first_frame"))
        elif reference_images:
            for b in reference_images[:9]:
                content.append(_img(b, "reference_image"))

        body: dict = {"model": model, "content": content, "generate_audio": generate_audio}
        if duration_seconds is not None:
            body["duration"] = int(duration_seconds)
        if aspect_ratio:
            body["ratio"] = aspect_ratio          # Seedance calls it `ratio`
        if resolution:
            body["resolution"] = resolution
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=_SUBMIT_TIMEOUT_SECS) as client:
            try:
                resp = await client.post(_TASKS_URL, headers=headers, json=body)
                resp.raise_for_status()
            except Exception as exc:
                raise SeedanceVideoError(f"submit failed: {exc}") from exc
            task_id = (resp.json() or {}).get("id")
            if not task_id:
                raise SeedanceVideoError("no task id in submission response.")

            url = await self._poll(client, headers, str(task_id))

            try:
                vresp = await client.get(url, timeout=_DOWNLOAD_TIMEOUT_SECS, follow_redirects=True)
                vresp.raise_for_status()
                data = vresp.content
            except Exception as exc:
                raise SeedanceVideoError(f"clip download failed: {exc}") from exc
            if not data:
                raise SeedanceVideoError("clip downloaded empty.")
            return data

    async def _poll(self, client, headers: dict, task_id: str) -> str:
        """Poll the task until terminal; return the result video_url."""
        for _ in range(int(_MAX_WAIT_SECS / _POLL_INTERVAL_SECS)):
            try:
                pr = await client.get(f"{_TASKS_URL}/{task_id}", headers=headers)
                pr.raise_for_status()
            except Exception as exc:
                raise SeedanceVideoError(f"poll failed: {exc}") from exc
            task = pr.json() or {}
            status = str(task.get("status") or "").lower()
            if status in _DONE_STATES:
                return _extract_video_url(task)
            if status in _FAIL_STATES:
                raise SeedanceVideoError(f"task {status}: {task.get('error') or task}")
            await asyncio.sleep(_POLL_INTERVAL_SECS)
        raise SeedanceVideoError("Seedance generation timed out after 10 minutes.")


def _extract_video_url(task: dict) -> str:
    """Dig the result video URL out of the task, tolerant of nesting."""
    paths = (
        ("content", "video_url"), ("video_url",), ("content", "url"),
        ("result", "video_url"), ("output", "video_url"),
    )
    for path in paths:
        cur = task
        for key in path:
            cur = cur.get(key) if isinstance(cur, dict) else None
        if isinstance(cur, str) and cur.startswith("http"):
            return cur
    raise SeedanceVideoError("no video_url in succeeded task.")
