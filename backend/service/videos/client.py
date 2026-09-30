"""The video backend seam: one interface, one error, one factory.

Video is a third provider inside a content run, resolved the way images are
(``agents.engines.resolve_video_run``): the conversation is on whichever key
the user brought for chat, the clips on whichever *video-capable* key they
brought. ``video_client_for`` is the only place a provider id becomes a client
class; the content tool calls it with what the session holds.

The error carries a code, not just a message, because the tool's answer
depends on it: "the filter refused this prompt" and "that first frame shows a
realistic person, which Seedance will not animate" ask the agent to do
different things, and "try again" is the right answer to neither.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from agents.models import Provider
from service.videos.schema import GenerateVideoRequest, GeneratedVideo, VideoFrame


class VideoErrorCode(StrEnum):
    SAFETY = "safety_blocked"       # the provider's filter refused the prompt or the output
    PERSON = "person_rejected"      # an input frame shows a realistic person the model will not animate
    TIMEOUT = "timeout"             # no clip before the deadline
    AUTH = "key_rejected"           # 401/403: the key is wrong, or has no access to this model
    BILLING = "no_credits"          # 402: the account behind the key cannot pay
    INVALID = "invalid_request"     # a 4xx the request itself caused
    PROVIDER = "provider_error"     # anything else upstream: 5xx, network, a malformed answer


class VideoAPIError(RuntimeError):
    """Any backend failure, classified."""

    label = "Video API"

    def __init__(
        self,
        message: str,
        *,
        model: str,
        code: VideoErrorCode = VideoErrorCode.PROVIDER,
        http_status: int | None = None,
    ):
        self.model = model
        self.code = code
        self.http_status = http_status
        self.detail = message
        super().__init__(f"{self.label} ({model}): [{code.value}] {message}")


class VideoClient(Protocol):
    """What every backend implements. Bytes in, bytes out; no DB, no disk.

    It returns when the clip is ready or raises: generation takes from ten
    seconds to several minutes, and the waiting (poll interval, deadline) is
    the backend's business, since each provider's job API differs."""

    async def generate_video(
        self,
        request: GenerateVideoRequest,
        *,
        first_frame: VideoFrame | None = None,
        last_frame: VideoFrame | None = None,
    ) -> GeneratedVideo: ...


def video_client_for(provider: Provider, api_key: str) -> VideoClient:
    """The client for a resolved video run. Imports are lazy, as for images."""
    if provider is Provider.GOOGLE_GENAI:
        from service.google.gemini.veo import GeminiVeoClient

        return GeminiVeoClient(api_key)
    if provider is Provider.OPENROUTER:
        from service.openrouter.videos import OpenRouterVideoClient

        return OpenRouterVideoClient(api_key)
    raise ValueError(f"{provider.value} has no video backend")
