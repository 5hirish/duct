"""Grok Imagine image-to-video (xAI) via the official ``xai-sdk`` — an alternative
video-gen provider to Veo.

The SDK call blocks until the clip is ready and returns its URL (it handles the
polling for us):

    client = xai_sdk.Client(api_key=...)
    response = client.video.generate(prompt=..., model="grok-imagine-video-1.5",
                                     image_url=..., duration=12)
    response.url  # temporary URL of the finished clip

We run that (sync) call in a thread and download the URL → mp4 bytes, mirroring
GeminiVeoClient's bytes-in / bytes-out contract. Grok Imagine 1.5 is
image-to-video with native audio; it has NONE of Veo's first+last interpolation /
reference-image / extension features.

The first frame is sent as a base64 data URI in ``image_url`` so it works in dev
(local keyframes) and prod (R2) alike — the image field accepts a data URI per the
docs. UNVALIDATED end-to-end: confirm the exact SDK surface with a spike + a real
XAI_API_KEY.
"""

from __future__ import annotations

import asyncio
import base64
import logging

from agents.models import VideoModel

logger = logging.getLogger(__name__)

# Single source of truth — the model id lives on the VideoModel enum.
DEFAULT_GROK_VIDEO_MODEL = VideoModel.GROK_IMAGINE_VIDEO_1_5.value

_DOWNLOAD_TIMEOUT_SECS = 120.0


class GrokVideoError(RuntimeError):
    """Raised on any Grok video-generation failure (generate / download)."""


class GrokVideoClient:
    """Wraps the xAI Grok Imagine video SDK. One instance per request is fine
    (mirrors GeminiVeoClient)."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("GrokVideoClient: api_key is required")
        import xai_sdk  # late import — only needed when a grok-* model is used

        self._client = xai_sdk.Client(api_key=api_key)

    async def generate_video(
        self,
        *,
        prompt: str,
        first_frame: bytes | None = None,
        first_frame_mime: str = "image/png",
        duration_seconds: int | None = None,
        model: str = DEFAULT_GROK_VIDEO_MODEL,
        **_veo_only,   # aspect_ratio / generate_audio / etc. — not used by Grok
    ) -> bytes:
        """Generate a clip and return its mp4 bytes. ``first_frame`` is the
        image-to-video opening frame (sent as a base64 data URI). Raises
        GrokVideoError on generation or download failure."""
        url = await asyncio.to_thread(
            self._run_generate, prompt, first_frame, first_frame_mime, duration_seconds, model
        )
        data = await asyncio.to_thread(_download_bytes, url)
        if not data:
            raise GrokVideoError("clip downloaded empty.")
        return data

    def _run_generate(
        self,
        prompt: str,
        first_frame: bytes | None,
        first_frame_mime: str,
        duration_seconds: int | None,
        model: str,
    ) -> str:
        kwargs: dict = {"prompt": prompt, "model": model}
        if first_frame is not None:
            b64 = base64.b64encode(first_frame).decode("ascii")
            kwargs["image_url"] = f"data:{first_frame_mime};base64,{b64}"
        if duration_seconds is not None:
            kwargs["duration"] = int(duration_seconds)
        try:
            resp = self._client.video.generate(**kwargs)
        except Exception as exc:
            raise GrokVideoError(f"generation failed: {exc}") from exc
        url = getattr(resp, "url", None)
        if not url:
            raise GrokVideoError("no video url in response.")
        return str(url)


def _download_bytes(url: str) -> bytes:
    import httpx

    resp = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT_SECS, follow_redirects=True)
    resp.raise_for_status()
    return resp.content
