"""Video generation across providers: Veo on a Gemini key
(``service/google/gemini/veo``), Seedance through OpenRouter
(``service/openrouter/videos``), chosen per run by
``agents.engines.resolve_video_run``.

Mirrors ``service/images``: the request and result shapes, the capability
table and the error live here because none of them belongs to one provider.
Clips are persisted like generated images (``service/generated_media``), as
``content_assets`` rows with a ``video/*`` type.
"""

from service.videos.caps import VIDEO_CAPS, VideoCaps, caps_for, fit_request
from service.videos.client import VideoAPIError, VideoClient, VideoErrorCode, video_client_for
from service.videos.schema import (
    GeneratedVideo,
    GenerateVideoRequest,
    VideoAspectRatio,
    VideoFrame,
    VideoResolution,
)

__all__ = [
    "VIDEO_CAPS",
    "GenerateVideoRequest",
    "GeneratedVideo",
    "VideoAPIError",
    "VideoAspectRatio",
    "VideoCaps",
    "VideoClient",
    "VideoErrorCode",
    "VideoFrame",
    "VideoResolution",
    "caps_for",
    "fit_request",
    "video_client_for",
]
