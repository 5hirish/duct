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
import time
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


def saved_reference_urls(db: Session, project_id: UUID) -> set[str]:
    """Every TikTok URL the project has saved as a discovered reference. Used to
    validate plan ``evidence`` so a citation can't be fabricated by the model —
    receipts are true by construction."""
    rows = db.exec(
        select(ContentAsset).where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == "discovered_reference",
        )
    ).all()
    return {r.url for r in rows if r.url}


# ---------------------------------------------------------------------------
# Media capture — runs as a FastAPI BackgroundTask after a post is saved, and
# via recapture_missing_media() as a backfill for tasks lost to a restart.
# ---------------------------------------------------------------------------

_IMG_CONTENT_TYPE = "image/jpeg"
_DOWNLOAD_ATTEMPTS = 2


def _download_to_bucket(src_url: str, key: str) -> str:
    """Fetch bytes from a (TikTok CDN) URL and store them in our bucket.
    Retries once on a transient miss. Returns the stored URL, or "" on failure."""
    if not src_url:
        return ""
    for attempt in range(_DOWNLOAD_ATTEMPTS):
        data = storage.get_bytes(src_url)
        if data:
            return storage.put_image(key, data, _IMG_CONTENT_TYPE)
        if attempt + 1 < _DOWNLOAD_ATTEMPTS:
            time.sleep(0.4)
    return ""


def capture_reference_media(asset_id: UUID, post: dict) -> None:
    """Persist a saved post's cover + slideshow images into our bucket, then
    patch the asset's ``params.media`` with a STATUS so the outcome is never
    silent:

      - ``ok``      — captured at least the cover or a slide
      - ``failed``  — had source URLs but every download failed (e.g. expired)
      - ``empty``   — nothing to capture (video with no cover/slides)

    Why: TikTok's CDN URLs are signed and expire within hours, so a saved
    reference loses its imagery unless we download the bytes promptly. Runs as a
    BackgroundTask on save and as a backfill via recapture_missing_media. Always
    best-effort — failures are logged, not raised. Video + subtitles need a
    re-scrape with download flags (Apify-metered) and are deferred to clone-time.
    """
    try:
        vm = post.get("video_meta") or {}
        slides_src = list(post.get("slideshow_image_links") or [])
        cover_src = vm.get("cover_url") or vm.get("original_cover_url") or (slides_src[0] if slides_src else "")
        had_sources = bool(cover_src or slides_src)

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

        captured = bool(media["cover"] or media["slides"])
        media["status"] = "ok" if captured else ("failed" if had_sources else "empty")

        # Always persist the marker (even on failure) so a lost/failed capture is
        # visible and recoverable, never a silent gap that breaks clone-time.
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
            "discover: media %s for asset=%s (cover=%s, slides=%d)",
            media["status"], asset_id, bool(media["cover"]), len(media["slides"]),
        )
    except Exception:
        logger.exception("discover: capture_reference_media failed for asset=%s", asset_id)


def recapture_missing_media(project_id: UUID, *, limit: int = 50) -> dict:
    """Backfill: re-attempt media capture for saved discoveries whose capture
    never ran (task lost to a restart → no ``params.media``) or failed.

    The TikTok CDN URLs expire within hours, so this only recovers recently
    saved posts; older ones re-mark ``failed`` so clone-time knows to re-scrape.
    Idempotent and safe to run repeatedly (cron-able later). Returns counts.
    """
    engine = get_engine()
    if engine is None:
        return {"scanned": 0, "recaptured": 0, "still_missing": 0, "pending": 0}

    with Session(engine) as db:
        rows = db.exec(
            select(ContentAsset).where(
                ContentAsset.project_id == project_id,
                ContentAsset.asset_type == "discovered_reference",
            ).order_by(ContentAsset.created_at.desc())  # type: ignore[union-attr]
        ).all()
        targets: list[tuple[UUID, dict]] = []
        for r in rows:
            params = r.params or {}
            media = params.get("media") or {}
            if not media or media.get("status") == "failed":
                targets.append((r.id, params.get("post") or {}))

    pending = max(0, len(targets) - limit)
    targets = targets[:limit]
    for asset_id, post in targets:
        capture_reference_media(asset_id, post)

    recaptured = still_missing = 0
    if targets:
        with Session(engine) as db:
            for asset_id, _ in targets:
                a = db.get(ContentAsset, asset_id)
                status = ((a.params or {}).get("media") or {}).get("status") if a else None
                if status == "ok":
                    recaptured += 1
                else:
                    still_missing += 1
    return {
        "scanned": len(targets),
        "recaptured": recaptured,
        "still_missing": still_missing,
        "pending": pending,
    }
