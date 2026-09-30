"""A video post's clip, as the tool, the routes and publishing all read it.

A clip is a ``content_assets`` row with a ``video/*`` type and its post id,
one row per take; the post's ``video`` column names the chosen one (the
*cut*) and carries what the viewport shows without a second query. Three
callers need the same answers — which takes a post has, what the cut is, and
which file publishing sends — so they are answered once, here, rather than in
``agents/content/tools.py`` and ``routes/content.py`` separately.

Framework-free: SQLModel and the asset model, nothing from an agent harness.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from models.content import ContentAsset, ContentPost

#: How many takes a post lists, newest first. The player shows these; older
#: ones stay in the media library.
MAX_TAKES = 6

VIDEO_POST_TYPE = "video"


def is_video_asset(asset: ContentAsset) -> bool:
    return str(asset.mime_type or "").startswith("video/")


def cut_of(asset: ContentAsset) -> dict[str, Any]:
    """What ``content_posts.video`` stores for a chosen take. Everything but
    the ids comes from the asset's own params, so re-choosing an older take
    restores its facts exactly."""
    params = asset.params or {}
    return {
        "asset_id": str(asset.id),
        "url": asset.url,
        "mime_type": asset.mime_type,
        "prompt": asset.prompt,
        "model": asset.model,
        "duration_seconds": params.get("duration_seconds"),
        "aspect_ratio": params.get("aspect_ratio"),
        "resolution": params.get("resolution"),
        "first_frame_url": params.get("first_frame_url") or "",
        "cost_usd": params.get("cost_usd"),
    }


def video_takes(db: Session, post: ContentPost) -> list[dict[str, Any]]:
    """The post's clips, newest first, each marked when it is the cut."""
    rows = db.exec(
        select(ContentAsset)
        .where(ContentAsset.post_id == post.id, ContentAsset.project_id == post.project_id)
        .where(ContentAsset.mime_type.like("video/%"))
        .order_by(ContentAsset.created_at.desc())
        .limit(MAX_TAKES)
    ).all()
    cut_id = str((post.video or {}).get("asset_id") or "")
    return [
        {**cut_of(row), "is_cut": str(row.id) == cut_id, "created_at": row.created_at.isoformat()}
        for row in rows
    ]


def take_for(db: Session, post: ContentPost, asset_id: Any) -> ContentAsset | None:
    """One of this post's clips by id, or None — never another post's."""
    try:
        row = db.get(ContentAsset, UUID(str(asset_id)))
    except ValueError:
        return None
    if row is None or row.post_id != post.id or row.project_id != post.project_id:
        return None
    return row if is_video_asset(row) else None


def publish_asset(db: Session, post: ContentPost) -> ContentAsset | None:
    """The one file a video post publishes: its cut, alone. None when the post
    has no clip yet, which the publish paths turn into "make one first"."""
    cut_id = (post.video or {}).get("asset_id")
    return take_for(db, post, cut_id) if cut_id else None
