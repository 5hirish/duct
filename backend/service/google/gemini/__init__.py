"""Gemini services — image generation and grounded web search.

Two capabilities Duct supplies as its own tools, backed by Gemini, so a model
that lacks them natively still has them. See search.py for why search in
particular cannot be the provider built-in.

The image client is one backend of ``service/images``; the request models,
persistence and the other backends live there.
"""

from service.google.gemini.client import GeminiAPIError, GeminiImageClient
from service.google.gemini.search import SEARCH_MODEL, search_web

__all__ = [
    "GeminiAPIError",
    "GeminiImageClient",
    "SEARCH_MODEL",
    "search_web",
]
