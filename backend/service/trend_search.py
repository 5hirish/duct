"""TikTok trend search for the content agent: Discover's search, read back as a summary.

Discover could search TikTok and the agent could only read what someone had
saved there, so a plan or a draft that needed "what's working this week" got
last month's saves or nothing. This runs the same two searches Discover runs,
through the same input policy (``service/apify/policy.py``) and the same run
cache, on the project owner's Apify key, and hands the agent a summary small
enough for its context: the top posts by plays, and what they have in common.

A search spends the owner's Apify credits like a Discover search does, so the
content runner caps it per turn (``TREND_SEARCHES_PER_RUN``), and the same
search inside the cache's window joins the earlier run instead of paying
again. Nothing is saved: a post worth keeping is saved from Discover, where
the person sees it.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from statistics import median
from typing import Any

from service.apify import ApifyAPIError, ApifyClient, ApifyRunStatus, ScrapedPost, get_default_actor_ids, run_cache
from service.apify.policy import MAX_TEXT, discover_run_input

logger = logging.getLogger(__name__)

# Discover's page size: a niche's top thirty is a pattern, a hundred is a bill.
RESULTS_PER_SEARCH = 30
# Hashtags in one search. The actor takes ten; past five a search stops
# describing one niche.
MAX_SEARCH_HASHTAGS = 5
DEFAULT_REGION = "US"

# What the agent reads back. Ten posts carry the hooks and formats; the rest
# of the thirty only add to the counts below.
TOP_POSTS = 10
TOP_TAGS = 8
TOP_SOUNDS = 5
CAPTION_CHARS = 200
# A tag or a sound on one post of thirty is an accident, not a pattern.
MIN_PATTERN_POSTS = 2

# Tags so broad they top every niche's list and say nothing about this one.
# The app's Discover read-out keeps the same list (app/src/lib/discoverSynthesis.js).
GENERIC_TAGS = frozenset({
    "fyp", "foryou", "foryoupage", "fy", "fypシ", "viral", "trending", "xyzbca", "parati",
})

# A hashtag run takes the actor one to three minutes; past this the search
# gives up and the run finishes on its own, where a retry inside the cache's
# window joins it instead of paying again.
SEARCH_TIMEOUT_SECONDS = 180.0
SEARCH_POLL_SECONDS = 3.0

_DEAD_RUN = frozenset({
    ApifyRunStatus.FAILED,
    ApifyRunStatus.ABORTING,
    ApifyRunStatus.ABORTED,
    ApifyRunStatus.TIMING_OUT,
    ApifyRunStatus.TIMED_OUT,
})


class TrendSearchFailed(RuntimeError):
    """The search did not come back. The message is for the agent to relay."""


def _tag(raw: str) -> str:
    return raw.strip().lstrip("#").lower()


def search_input(hashtags: Sequence[str], region: str) -> tuple[str, dict[str, Any], str]:
    """The actor, its input and a one-line name for the search.

    Hashtags search by tag; none reads a region's trend feed. The input goes
    through Discover's policy, so the agent can ask for nothing a person on
    the Discover tab could not.
    """
    actors = get_default_actor_ids()
    tags = list(dict.fromkeys(t for t in (_tag(h) for h in hashtags) if t))[:MAX_SEARCH_HASHTAGS]
    if tags:
        actor = actors["post_by_hashtag"]
        payload = {"hashtags": tags, "resultsPerPage": RESULTS_PER_SEARCH}
        query = " ".join(f"#{t}" for t in tags)
    else:
        actor = actors["trend_feed"]
        code = (region or DEFAULT_REGION).strip().upper()[:MAX_TEXT]
        payload = {"region": code, "resultsPerPage": RESULTS_PER_SEARCH}
        query = f"trending in {code}"
    try:
        return actor, discover_run_input(actor, payload), query
    except ValueError as exc:
        raise TrendSearchFailed(f"That search is not one Discover can run ({exc}).") from exc


def _engagement(p: ScrapedPost) -> float:
    if not p.play_count:
        return 0.0
    return (p.digg_count + p.comment_count + p.share_count + p.collect_count) / p.play_count


def _post_row(p: ScrapedPost) -> dict[str, Any]:
    return {
        "url": p.web_video_url,
        "caption": p.text[:CAPTION_CHARS],
        "format": "slideshow" if p.is_slideshow else "video",
        "plays": p.play_count,
        "saves": p.collect_count,
        "shares": p.share_count,
        "comments": p.comment_count,
        "engagement": round(_engagement(p), 4),
        "hashtags": p.hashtags[:6],
        "sound": p.music_meta.music_name if p.music_meta else "",
        "author": p.author_meta.name if p.author_meta else "",
        "posted_at": p.create_time_iso.date().isoformat() if p.create_time_iso else None,
    }


def _counted(values: list[str], top: int) -> list[dict[str, Any]]:
    return [
        {"name": name, "posts": n}
        for name, n in Counter(values).most_common()
        if n >= MIN_PATTERN_POSTS
    ][:top]


def _format_mix(posts: list[ScrapedPost]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, group in (("slideshow", [p for p in posts if p.is_slideshow]),
                         ("video", [p for p in posts if not p.is_slideshow])):
        # Median, not mean: one post at 40% on 300 views would decide the winner.
        out[label] = {
            "posts": len(group),
            "median_engagement": round(median(_engagement(p) for p in group), 4) if group else None,
        }
    return out


def summarise(posts: list[ScrapedPost], query: str) -> dict[str, Any]:
    """What the agent reads: the top posts by plays and what they share.

    ``query`` and ``sources`` are named as WebSearch names them, so the
    activity row draws the search the same way live and on a reload.
    """
    ranked = sorted(posts, key=lambda p: p.play_count, reverse=True)
    top = ranked[:TOP_POSTS]
    tags = [t for p in posts for t in {_tag(h) for h in p.hashtags} if t and t not in GENERIC_TAGS]
    sounds = [p.music_meta.music_name for p in posts if p.music_meta and p.music_meta.music_name]
    return {
        "query": query,
        "found": len(posts),
        "posts": [_post_row(p) for p in top],
        "patterns": {
            "formats": _format_mix(posts),
            "hashtags": _counted(tags, TOP_TAGS),
            "sounds": _counted(sounds, TOP_SOUNDS),
        },
        "sources": [
            {"title": (f"@{p.author_meta.name}" if p.author_meta and p.author_meta.name else p.text[:60]), "url": p.web_video_url}
            for p in top
            if p.web_video_url
        ],
    }


async def run_trend_search(
    client: ApifyClient,
    hashtags: Sequence[str] = (),
    region: str = "",
    *,
    timeout: float = SEARCH_TIMEOUT_SECONDS,
    poll: float = SEARCH_POLL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    """Run one search and summarise it. Raises ``TrendSearchFailed`` for every
    way it can fail, with a sentence the agent can pass on."""
    actor, payload, query = search_input(hashtags, region)
    try:
        run, reused = await run_cache.apify_runs.start(client, actor, payload)
        waited = 0.0
        while run.status is not ApifyRunStatus.SUCCEEDED and run.status not in _DEAD_RUN:
            if waited >= timeout:
                raise TrendSearchFailed(
                    f"The TikTok search for {query} is still running after {timeout:.0f} s. "
                    "Searching again in a few minutes picks up the same run at no extra cost."
                )
            await sleep(poll)
            waited += poll
            run = await client.get_run(run.id)
        if run.status is not ApifyRunStatus.SUCCEEDED:
            raise TrendSearchFailed(f"The TikTok search for {query} ended {run.status.value.lower()} on Apify.")
        posts = await client.get_dataset_posts(run.default_dataset_id, limit=RESULTS_PER_SEARCH)
    except ApifyAPIError as exc:
        raise TrendSearchFailed(f"Apify refused the search ({exc.status_code}): {exc.message}") from exc
    logger.info("trend search: %s run %s for %s, %d posts", "reused" if reused else "started", run.id, query, len(posts))
    return summarise(posts, query)
