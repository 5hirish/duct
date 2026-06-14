"""Typed result models for content MCP tools.

Tool handlers return JSON text blocks the model reads and feeds back (e.g.
``asset_ids`` → ``input_asset_ids``, ``attached_to``, ``asset_url``). Modeling
those results makes the contract explicit and validated instead of hand-built
``json.dumps`` dicts scattered across handlers. Serialize via
``tools._ok_model`` (text-only) or ``tools._ok_with_images`` (image + text).

Relational preconditions ("slide_id exists on THIS post") are enforced by the
``_require_*`` runtime guards in ``tools.py`` — those are about live state, which
a static schema can't express; these models are the *shape* contract.
"""

from __future__ import annotations

from pydantic import BaseModel


class GenerateImageResult(BaseModel):
    asset_ids: list[str]
    asset_urls: list[str]
    model: str
    attached_to: str | None = None  # slide_id the image was attached to, or null


class EditImageResult(BaseModel):
    asset_ids: list[str]
    asset_urls: list[str]
    model: str


class RenderSlideResult(BaseModel):
    slide_id: str
    asset_url: str
    width: int = 1080
    height: int = 1920
    note: str = ""


class EditSlideResult(BaseModel):
    post_id: str
    slide_id: str
    updated: list[str]  # the patched field names
