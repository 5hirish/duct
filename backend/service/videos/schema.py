"""The shapes a video backend takes and returns. Provider-neutral on purpose:
each backend translates these into its own request, the way the image backends
translate ``GenerateImageRequest``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agents.models import VideoModel


class VideoAspectRatio(StrEnum):
    """The ratios at least one video model serves. 9:16 first: a TikTok is."""

    PORTRAIT_9_16  = "9:16"
    LANDSCAPE_16_9 = "16:9"
    SQUARE_1_1     = "1:1"
    PORTRAIT_3_4   = "3:4"
    LANDSCAPE_4_3  = "4:3"
    LANDSCAPE_21_9 = "21:9"


class VideoResolution(StrEnum):
    """Ascending. 4K is left out: nothing Duct publishes to shows it, Seedance
    stops at 720p, and on Veo it is half again the price of 1080p."""

    P480  = "480p"
    P720  = "720p"
    P1080 = "1080p"


class GenerateVideoRequest(BaseModel):
    """One clip. Frames travel beside this as bytes (``VideoFrame``), the same
    split as image references, so the request stays a small validated value."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    model: VideoModel
    duration_seconds: int = Field(8, ge=1, le=60)
    aspect_ratio: VideoAspectRatio = VideoAspectRatio.PORTRAIT_9_16
    resolution: VideoResolution = VideoResolution.P720
    negative_prompt: str | None = None


@dataclass(frozen=True)
class VideoFrame:
    """A first or last frame. ``url`` is set when the image already has a
    public https address, which a gateway can fetch instead of a data URI."""

    data: bytes
    mime_type: str
    url: str = ""


@dataclass(frozen=True)
class GeneratedVideo:
    """What a backend hands back: the file, and what the provider says it cost
    when it says (OpenRouter does; Veo is priced from the table instead)."""

    data: bytes
    mime_type: str = "video/mp4"
    cost_usd: float | None = None
