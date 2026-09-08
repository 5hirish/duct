"""The image backend seam: one interface, one error, one factory.

Images are a second provider inside a content run. The conversation is on
whichever provider the user brought a key for; the pictures come from
whichever *image-capable* provider they brought a key for, which need not be
the same one. Until this seam existed that second provider was hard-wired to
Gemini, so a user on an OpenAI key was told to go and get a Google key for
something their own key could already do.

``image_client_for`` is the only place a provider id turns into a client
class. The content tools call it with what ``resolve_image_run`` stashed on
the session and never name a backend themselves.
"""

from __future__ import annotations

from typing import Protocol

from agents.models import Provider
from service.images.schema import EditImageRequest, GenerateImageRequest, GeneratedImage


class ImageAPIError(RuntimeError):
    """Any backend failure. Carries model + http_status when known.

    The tools catch this and nothing more specific: the user-facing sentence
    is the same whichever provider declined, and the detail goes to the log.
    """

    #: Shown in the message so a log line says which service answered.
    label = "Image API"

    def __init__(self, message: str, *, model: str, http_status: int | None = None):
        self.model = model
        self.http_status = http_status
        super().__init__(f"{self.label} ({model}): {message}")


class ImageClient(Protocol):
    """What every backend implements. Bytes in, bytes out; no DB, no disk."""

    async def generate_image(
        self,
        request: GenerateImageRequest,
        *,
        input_bytes: bytes | None = None,
        input_bytes_list: list[bytes] | None = None,
    ) -> list[GeneratedImage]: ...

    async def edit_image(
        self,
        request: EditImageRequest,
        *,
        base_bytes: bytes,
        mask_bytes: bytes | None = None,
        style_bytes: bytes | None = None,
        subject_bytes: bytes | None = None,
    ) -> list[GeneratedImage]: ...


def image_client_for(provider: Provider, api_key: str) -> ImageClient:
    """The client for a resolved image run. Imports are lazy on purpose: each
    backend pulls its own SDK, and a Gemini run should not pay for OpenAI's."""
    if provider is Provider.GOOGLE_GENAI:
        from service.google.gemini.client import GeminiImageClient

        return GeminiImageClient(api_key)
    if provider is Provider.OPENAI:
        from service.openai.images import OpenAIImageClient

        return OpenAIImageClient(api_key)
    if provider is Provider.XAI:
        from service.xai.images import XAIImageClient

        return XAIImageClient(api_key)
    raise ValueError(f"{provider.value} has no image backend")
