"""Typed shapes for Higgsfield video generation + persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(kw_only=True)
class VideoAsset:
    """A persisted video clip — the handle the agent tool returns after a
    Higgsfield clip has been downloaded and stored as a content_assets row.
    Parallels service/gemini/schema.py:ImageAsset.
    """

    asset_id: UUID
    url: str                       # opaque public URL (R2 CDN) or /uploads/... (local)
    mime_type: str = "video/mp4"
    duration_seconds: int | None = None
    prompt: str = ""
    model: str = ""
    params: dict = field(default_factory=dict)
