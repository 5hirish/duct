"""Shared read path for the TikTok discovery feature.

Discovered posts are persisted as ``ContentAsset`` rows
(``asset_type='discovered_reference'``, ``source='apify'``) by
``routes/content.py::discover_save``. This module is the single query helper so
every consumer sees the same shape. Today the sole consumer is the Content
Planner's ``trend_scout`` sub-agent (the Content Studio agent no longer reads
discovery — planning owns it).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from db.session import get_engine
from models.content import ContentAsset
from service import storage

logger = logging.getLogger(__name__)


def query_discovered_references(
    db: Session,
    project_id: UUID,
    *,
    min_plays: int = 10000,
    limit: int = 30,
) -> list[dict]:
    """Return saved high-performing TikTok posts for a project, newest first,
    filtered to ``play_count >= min_plays``. Shape mirrors what the agent cites
    (``asset_id`` + ``tiktok_url`` for evidence, plus engagement + metadata).
    """
    rows = db.exec(
        select(ContentAsset)
        .where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == "discovered_reference",
        )
        .order_by(ContentAsset.created_at.desc())  # type: ignore[union-attr]
        .limit(200)  # over-fetch; filter in Python by min_plays
    ).all()

    items: list[dict] = []
    for r in rows:
        p = (r.params or {}).get("post") or {}
        if (p.get("play_count") or 0) < min_plays:
            continue
        items.append({
            "asset_id":      str(r.id),
            "tiktok_url":    r.url,
            "play_count":    p.get("play_count"),
            "digg_count":    p.get("digg_count"),
            "comment_count": p.get("comment_count"),
            "share_count":   p.get("share_count"),
            "collect_count": p.get("collect_count"),
            "hashtags":      p.get("hashtags") or [],
            "music":         (p.get("music_meta") or {}).get("music_name"),
            "author":        (p.get("author_meta") or {}).get("name"),
            "is_slideshow":  p.get("is_slideshow"),
            "text":          (p.get("text") or "")[:280],
            "created_at":    p.get("create_time_iso"),
        })
        if len(items) >= limit:
            break
    return items


# ---------------------------------------------------------------------------
# Media capture — runs as a FastAPI BackgroundTask after a post is saved.
# ---------------------------------------------------------------------------

_IMG_CONTENT_TYPE = "image/jpeg"


def _download_to_bucket(src_url: str, key: str) -> str:
    """Fetch bytes from a (TikTok CDN) URL and store them in our bucket.
    Returns the stored URL, or "" if the source couldn't be fetched."""
    if not src_url:
        return ""
    data = storage.get_bytes(src_url)
    if not data:
        return ""
    return storage.put_image(key, data, _IMG_CONTENT_TYPE)


def capture_reference_media(asset_id: UUID, post: dict) -> None:
    """Background job: persist a saved post's cover + slideshow images into our
    bucket, then patch the asset's ``params.media``.

    Why: TikTok's CDN URLs are signed and expire within hours, so a saved
    reference would lose its imagery (and can't be analysed later) unless we
    download the bytes now. Best-effort — any failure is logged, not raised, so
    a flaky CDN never breaks the save. Video + subtitles need a re-scrape with
    download flags (Apify-metered) and are deferred until the analysis feature
    that would consume them exists.
    """
    try:
        vm = post.get("video_meta") or {}
        slides_src = list(post.get("slideshow_image_links") or [])
        cover_src = vm.get("cover_url") or vm.get("original_cover_url") or (slides_src[0] if slides_src else "")

        media: dict = {
            "cover": "",
            "slides": [],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        cover_url = _download_to_bucket(cover_src, f"discover/{asset_id}/cover.jpg")
        if cover_url:
            media["cover"] = cover_url
        for i, s in enumerate(slides_src):
            stored = _download_to_bucket(s, f"discover/{asset_id}/slide-{i:02d}.jpg")
            if stored:
                media["slides"].append(stored)

        if not media["cover"] and not media["slides"]:
            logger.info("discover: no media captured for asset=%s", asset_id)
            return

        engine = get_engine()
        if engine is None:
            return
        with Session(engine) as db:
            asset = db.get(ContentAsset, asset_id)
            if asset is None:
                return
            params = dict(asset.params or {})
            params["media"] = media
            asset.params = params  # reassign so SQLAlchemy detects the JSONB change
            db.add(asset)
            db.commit()
        logger.info(
            "discover: captured media for asset=%s (cover=%s, slides=%d)",
            asset_id, bool(media["cover"]), len(media["slides"]),
        )
    except Exception:
        logger.exception("discover: capture_reference_media failed for asset=%s", asset_id)
