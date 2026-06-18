"""Shared read path for the TikTok discovery feature.

Discovered posts are persisted as ``ContentAsset`` rows
(``asset_type='discovered_reference'``, ``source='apify'``) by
``routes/content.py::discover_save``. This module is the single query helper so
every consumer sees the same shape. Today the sole consumer is the Content
Planner's ``trend_scout`` sub-agent (the Content Studio agent no longer reads
discovery — planning owns it).
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from models.content import ContentAsset


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
