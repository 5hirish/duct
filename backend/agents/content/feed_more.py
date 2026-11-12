"""What the project published (its RSS and Atom feeds) and its milestones,
as feeds for a plan from shipped work (#564).

Read by code before the model starts, like GitHub: through FetchData for the
feeds (``rss_items``) and the GA4 series (``ga4_weekly_users``), and one
bounded GitHub read for the stars. Each source that cannot be read leaves a
note; none fails the read.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import Counter
from datetime import date
from typing import Any
from uuid import UUID

from agents.content.feed import FeedItem, FeedSource, LeftOut
from agents.content.feed_mcp import McpFeed
from agents.content.milestones import best_week, history_window, star_milestone

logger = logging.getLogger(__name__)

RSS_ENTITY = "rss_items"
GA4_WEEKS_ENTITY = "ga4_weekly_users"
POST = "post"
MAX_POSTS = 15


def rss_items(rows: list[dict[str, Any]], *, already: set[str]) -> tuple[list[FeedItem], Counter]:
    """Feed entries as stories, newest first, cited by their link."""
    left: Counter = Counter()
    kept: list[FeedItem] = []
    seen: set[str] = set()
    for row in rows:
        link, title = str(row.get("link") or ""), str(row.get("title") or "").strip()
        if not title or not link:
            continue
        ref = f"rs:{hashlib.sha256(link.encode()).hexdigest()[:10]}"
        if ref in seen:
            continue
        seen.add(ref)
        if ref in already:
            left[LeftOut.ALREADY_PLANNED] += 1
            continue
        kept.append(FeedItem(ref=ref, kind=POST, title=title, url=link, at=str(row.get("published") or ""),
                             detail=str(row.get("feed") or "")))
    kept.sort(key=lambda i: i.at, reverse=True)
    if len(kept) > MAX_POSTS:
        left[LeftOut.OVER_CAP] += len(kept) - MAX_POSTS
        kept = kept[:MAX_POSTS]
    return kept, left


async def read_published_and_milestones(
    user_id: UUID, project_id: UUID, sources: list[FeedSource], window: tuple[date, date], *, already: set[str],
) -> McpFeed:
    from agents.insights.fetchers import fetch_entity

    out = McpFeed()
    if FeedSource.RSS in sources:
        fetched = await asyncio.to_thread(
            fetch_entity, RSS_ENTITY, user_id=user_id, project_id=project_id,
            date_from=window[0].isoformat(), date_to=window[1].isoformat(),
        )
        if fetched.get("status") == "ok":
            kept, left = rss_items(_rows(fetched), already=already)
            out.items += kept
            out.left_out.update(left)
            data = fetched.get("data") if isinstance(fetched.get("data"), dict) else {}
            for error in (data.get("errors") or [])[:3]:
                out.notes.append(str(error))
        else:
            out.notes.append("No feeds are connected for this project, so nothing was read from RSS.")

    if FeedSource.MILESTONES in sources:
        try:
            star = await asyncio.to_thread(_stars, user_id, project_id, window, already)
        except Exception:  # noqa: BLE001 — a refused star read is a note, never a failed plan
            logger.warning("feed: star milestone read failed", exc_info=True)
            star = None
        if star is not None:
            out.items.append(star)
        since, until = history_window(window)
        weekly = await asyncio.to_thread(
            fetch_entity, GA4_WEEKS_ENTITY, user_id=user_id, project_id=project_id, date_from=since, date_to=until,
        )
        if weekly.get("status") == "ok":
            week = best_week(_rows(weekly), window, already=already)
            if week is not None:
                out.items.append(week)
    return out


def _rows(fetched: dict) -> list[dict]:
    data = fetched.get("data")
    if isinstance(data, dict):
        data = data.get("data") or data.get("rows")
    return [r for r in (data or fetched.get("rows") or []) if isinstance(r, dict)]


def _stars(user_id, project_id, window, already) -> FeedItem | None:
    from service.github.access import bound_read_credentials
    from service.github.fetch import recent_stars

    creds = bound_read_credentials(user_id, project_id)
    if creds is None:
        return None
    total, dates, _reached = recent_stars(creds, window[0].isoformat())
    return star_milestone(total, dates, window, repo=creds["repo"], already=already)
