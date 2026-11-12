"""Milestones as a feed (#564): the moments people share that no commit
records, worked out in code from connectors the project already has.

Two, the issue's smallest version:

* **GitHub stars passing a round number** inside the window. The count before
  the window is the count now minus the stars dated inside it, read from the
  newest end of the stargazers list. No stored state: the list has the dates.
  When the read cannot reach the window's start (a very busy window), the
  count before is an upper bound, so a threshold above it was still crossed;
  nothing is claimed that the data does not prove.
* **GA4's best week yet**: the newest complete ISO week beating every week
  before it, with at least ``MIN_PRIOR_WEEKS`` of history, so a new property's
  second week is not "best ever".

Revenue milestones are deliberately absent: a figure from Stripe or
RevenueCat says something a founder may not want posted, and the issue keeps
it off until they turn it on.

Plain functions over plain rows; the reads are the runner's.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from agents.content.feed import FeedItem

MILESTONE = "milestone"
STAR_THRESHOLDS = (10, 25, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000)
MIN_PRIOR_WEEKS = 4
WEEKS_OF_HISTORY = 52


def star_milestone(total: int, newest_first: list[str], window: tuple[date, date], *,
                   repo: str, already: set[str]) -> FeedItem | None:
    """The highest round star count crossed inside the window, or None.
    ``newest_first`` holds the ``starred_at`` dates (ISO) back to at least the
    window's start, or as far as the read reached."""
    start, end = window
    inside = [d for d in newest_first if d and start.isoformat() <= d[:10] <= end.isoformat()]
    before = total - len(inside)
    crossed = [t for t in STAR_THRESHOLDS if before < t <= total]
    if not crossed:
        return None
    threshold = max(crossed)
    ref = f"ms:stars-{threshold}"
    if ref in already:
        return None
    # The star that made the threshold is the (total - threshold)th from the newest.
    index = total - threshold
    at = newest_first[index][:10] if index < len(newest_first) else end.isoformat()
    return FeedItem(
        ref=ref, kind=MILESTONE, title=f"{threshold:,} GitHub stars",
        detail=f"{total:,} now; {len(inside):,} new in the window",
        url=f"https://github.com/{repo}/stargazers", at=at,
    )


def _sunday(iso_week: str) -> date | None:
    try:
        return date.fromisocalendar(int(iso_week[:4]), int(iso_week[4:]), 7)
    except (ValueError, TypeError):
        return None


def best_week(rows: list[dict[str, Any]], window: tuple[date, date], *, already: set[str]) -> FeedItem | None:
    """The newest complete week that beat every week before it, when it ends
    inside the window. A week still running on the window's last day is
    partial and is left out rather than compared."""
    start, end = window
    weeks = sorted(
        ((str(r.get("iso_week") or ""), int(r.get("active_users") or 0)) for r in rows if r.get("iso_week")),
        key=lambda w: w[0],
    )
    weeks = [w for w in weeks if (_sunday(w[0]) or end + timedelta(days=1)) <= end]
    if len(weeks) <= MIN_PRIOR_WEEKS:
        return None
    (week, users), prior = weeks[-1], weeks[:-1]
    sunday = _sunday(week)
    if sunday is None or sunday < start or users <= max(u for _, u in prior):
        return None
    ref = f"ms:ga4-week-{week}"
    if ref in already:
        return None
    runner_up = max(u for _, u in prior)
    return FeedItem(
        ref=ref, kind=MILESTONE, title=f"Best week yet: {users:,} active users",
        detail=f"Up from a previous best of {runner_up:,}, over {len(prior)} weeks", at=sunday.isoformat(),
    )


def history_window(window: tuple[date, date]) -> tuple[str, str]:
    """The GA4 read a best-week check needs: a year back to the window's end."""
    return (window[1] - timedelta(weeks=WEEKS_OF_HISTORY)).isoformat(), window[1].isoformat()
