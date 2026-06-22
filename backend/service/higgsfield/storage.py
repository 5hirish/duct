"""Persist a generated Higgsfield video clip.

Parallels service/gemini/storage.py:persist_generated_image — write the bytes to
the configured object store (R2 in prod, local disk in dev) under the same
projects/{project_id}/generated/<uuid>.<ext> layout, insert a content_assets
row, and return a VideoAsset handle. content_assets has no enum constraint on
mime_type/source/asset_type, so "video/mp4" + source="higgsfield" need no schema
change.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

import httpx
from sqlmodel import Session

from models.content import ContentAsset
from service import storage
from service.higgsfield.schema import VideoAsset

logger = logging.getLogger(__name__)

_MIME_TO_EXT = {
    "video/mp4":       "mp4",
    "video/webm":      "webm",
    "video/quicktime": "mov",
}

# Generated clips can be a few MB and Higgsfield's CDN may be slow on first hit —
# allow far more headroom than the 20s image-reference fetch in service/storage.
_DOWNLOAD_TIMEOUT_SECS = 120.0


def download_video_bytes(source_url: str) -> bytes:
    """Fetch a finished clip from Higgsfield's result URL. Raises on failure
    (the caller surfaces a friendly error to the agent)."""
    resp = httpx.get(source_url, timeout=_DOWNLOAD_TIMEOUT_SECS, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def persist_generated_video(
    project_id: UUID,
    *,
    db: Session,
    data: bytes,
    mime_type: str = "video/mp4",
    prompt: str,
    model: str,
    params: dict,
    duration_seconds: int | None = None,
    post_id: UUID | None = None,
    source: str = "higgsfield",
) -> VideoAsset:
    """Store ``data`` and insert a ContentAsset row; return a VideoAsset handle."""
    ext = _MIME_TO_EXT.get(mime_type, "mp4")
    asset_id = uuid4()
    filename = f"{asset_id}.{ext}"
    key = f"projects/{project_id}/generated/{filename}"
    public_url = storage.put_image(key, data, mime_type)  # mime-generic despite the name

    row = ContentAsset(
        id=asset_id,
        project_id=project_id,
        post_id=post_id,
        asset_type="generated",
        source=source,
        url=public_url,
        filename=filename,
        mime_type=mime_type,
        prompt=prompt,
        model=model,
        params=params,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("higgsfield: persisted video asset %s (%d bytes) → %s", asset_id, len(data), public_url)

    return VideoAsset(
        asset_id=row.id,
        url=public_url,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
        prompt=prompt,
        model=model,
        params=params,
    )
