"""When a text post should go out (issue #266): the next good slot for a
channel, from the account's own history when there is enough of it.

``performance.best_posting_times`` answers the same question for a plan's
visual posts and deliberately leaves text out: a tweet's numbers must not
steer a TikTok plan. This is the other half: X and LinkedIn slots from X and
LinkedIn posts, whose numbers are typed in by hand (PostBridge reports
neither), so the history is thin for a long time and the default carries
most accounts at first. The reason rides with the slot, so the person knows
which one they are looking at.

Times are the reader's own: the history's hours are read in their timezone,
and the slot is a wall-clock hour there. No DB here; the route passes the
posts in.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from service.content_metrics import metric_value

# Enough posts with numbers to trust an hour over the default, and enough in
# an hour to call it a pattern rather than one good post.
MIN_POSTS = 5
MIN_PER_HOUR = 2
# Two posts on one channel closer than this compete for the same feed.
SPACING = timedelta(hours=3)
# A slot is never sooner than this: the person needs a moment to change it.
LEAD = timedelta(minutes=15)
LOOKAHEAD_DAYS = 14

# The widely cited defaults for a B2B audience: X on weekday mornings,
# LinkedIn mid-week before work. Monday is 0.
DEFAULTS: dict[str, tuple[frozenset[int], int]] = {
    "twitter": (frozenset({0, 1, 2, 3, 4}), 9),
    "linkedin": (frozenset({1, 2, 3}), 8),
}
_FALLBACK = (frozenset({0, 1, 2, 3, 4}), 9)

REASON_HISTORY = "history"
REASON_DEFAULT = "default"


@dataclass(frozen=True)
class BestSlot:
    at: datetime        # UTC
    reason: str         # REASON_HISTORY | REASON_DEFAULT
    posts: int          # posts with numbers the choice was made from
    hour: int           # the local hour


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def engagement(perf: dict | None) -> float | None:
    """One number per post to rank hours by: views where the platform gave
    them, else likes plus comments. None when the post has neither."""
    views = metric_value(perf, "views")
    if views is not None:
        return float(views)
    likes, comments = metric_value(perf, "likes"), metric_value(perf, "comments")
    if likes is None and comments is None:
        return None
    return float((likes or 0) + (comments or 0))


def best_hour(posts: list, tz: ZoneInfo) -> tuple[int | None, int]:
    """The local hour whose posts did best, by median, and how many posts
    with numbers there were. None when there are too few to say."""
    by_hour: dict[int, list[float]] = {}
    counted = 0
    for p in posts:
        score = engagement(getattr(p, "perf", None))
        posted = getattr(p, "posted_at", None)
        if score is None or posted is None:
            continue
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        by_hour.setdefault(posted.astimezone(tz).hour, []).append(score)
        counted += 1
    eligible = {h: s for h, s in by_hour.items() if len(s) >= MIN_PER_HOUR}
    if counted < MIN_POSTS or not eligible:
        return None, counted
    return max(eligible, key=lambda h: (statistics.median(eligible[h]), len(eligible[h]))), counted


def next_slot(
    channel: str,
    *,
    posts: list,
    taken: list[datetime],
    now: datetime,
    tz_name: str | None = None,
) -> BestSlot:
    """The next good slot for a post on ``channel``: the account's best hour
    when its history says so, else the channel's default; never within
    ``SPACING`` of a post already scheduled on the channel."""
    tz = zone(tz_name)
    days, default_hour = DEFAULTS.get(channel, _FALLBACK)
    hour, counted = best_hour(posts, tz)
    reason = REASON_HISTORY if hour is not None else REASON_DEFAULT
    if hour is None:
        hour = default_hour
    else:
        # The account's own best hour holds on any day X is read, and on
        # LinkedIn's working week.
        days = frozenset(range(7)) if channel == "twitter" else frozenset(range(5))
    earliest = now + LEAD
    local_today = earliest.astimezone(tz).date()
    for offset in range(LOOKAHEAD_DAYS):
        day = local_today + timedelta(days=offset)
        if day.weekday() not in days:
            continue
        at = datetime.combine(day, time(hour), tzinfo=tz).astimezone(timezone.utc)
        if at < earliest:
            continue
        if any(abs(at - t) < SPACING for t in taken):
            continue
        return BestSlot(at=at, reason=reason, posts=counted, hour=hour)
    # Every slot in two weeks is taken: the first free hour after the last one.
    last = max(taken, default=earliest)
    return BestSlot(at=last + SPACING, reason=reason, posts=counted, hour=hour)


__all__ = ["BestSlot", "DEFAULTS", "MIN_POSTS", "REASON_DEFAULT", "REASON_HISTORY", "best_hour", "next_slot", "zone"]
