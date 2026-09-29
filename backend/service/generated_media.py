"""Write generated media to the object store and record it as a content asset.

One body for every generated kind. Images had it to themselves until video
became the second caller, and a video run cannot go through the image
helper as it stood: that mapped any type it did not know to ``.png``, so an
mp4 would have been stored under a picture's extension.

The URL is absolute (R2 CDN) or relative (``/uploads/...`` on the local
backend); the rest of the app treats it as an opaque public URL. See
``service/storage.py`` for how the backend is chosen.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlmodel import Session

from models.content import ContentAsset
from service import storage

EXTENSIONS: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
}


def persist_generated_media(
    project_id: UUID,
    data: bytes,
    mime_type: str,
    *,
    db: Session,
    prompt: str,
    model: str,
    params: dict,
    post_id: UUID | None = None,
    source: str,
) -> ContentAsset:
    """Store ``data`` under ``projects/{project_id}/generated/`` and insert its
    ``content_assets`` row. An unknown type keeps its bytes and gets ``.bin``
    rather than an extension that lies about them."""
    ext = EXTENSIONS.get(mime_type, "bin")
    asset_id = uuid4()
    filename = f"{asset_id}.{ext}"
    public_url = storage.put_image(f"projects/{project_id}/generated/{filename}", data, mime_type)

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
    return row
