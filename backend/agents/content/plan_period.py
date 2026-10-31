"""The period a content plan manages: which dates, and how many posts.

A plan is not a one-off document. It is the plan for a stretch of the
calendar — one post per day, laid on sequential dates from ``start_date`` —
and the Plan tab manages it: revising it changes that plan, it does not
leave a second one beside it. So a plan's period is fixed when it is made
and every later ``submit_plan`` for it keeps the same dates.

The person picks how far ahead: the month in progress (the default), or the
next 7, 14 or 30 days. Any period is at most ``MAX_PLAN_DAYS`` long, so a
31-day month started on the 1st is planned to the 30th. A month with less
than ``ROLLOVER_DAYS`` left is planned from the next month instead.

One plan per period. A run opened while a plan already covers its first date
manages that plan instead of making another, and a new plan stops short of
the next plan already made (the runner's ``_resolve_plan_period``). The app
mirrors these rules in ``app/src/lib/contentSchedule.js`` so its buttons can
name the dates before the run starts.

No DB here.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

MAX_PLAN_DAYS = 30

# The last few days of a month are not a month's plan, and someone opening
# the Plan tab on the 28th is already thinking about the next one.
ROLLOVER_DAYS = 7


@dataclass(frozen=True)
class PlanPeriod:
    start: date
    days: int

    @property
    def end(self) -> date:
        return self.start + timedelta(days=self.days - 1)

    def label(self) -> str:
        """'October 2026' for the rest of a month, else 'Oct 7 – Oct 13, 2026'."""
        s, e = self.start, self.end
        if (s.year, s.month) == (e.year, e.month) and e == _month_end(e):
            return s.strftime("%B %Y")
        return f"{s:%b} {s.day} – {e:%b} {e.day}, {e.year}"

    def stopping_before(self, next_start: date | None) -> PlanPeriod:
        """This period cut short of a plan that starts inside it."""
        if next_start is None or not self.start < next_start <= self.end:
            return self
        return PlanPeriod(self.start, (next_start - self.start).days)


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def plan_end(start: date | None, n_days: int) -> date | None:
    """The last date a stored plan covers; None for a plan with no start."""
    if start is None or n_days <= 0:
        return None
    return start + timedelta(days=n_days - 1)


def month_period(start: date) -> PlanPeriod:
    """The rest of ``start``'s month, or the whole of the next one when less
    than ``ROLLOVER_DAYS`` of it are left."""
    end = _month_end(start)
    if (end - start).days + 1 < ROLLOVER_DAYS:
        start = end + timedelta(days=1)
        end = _month_end(start)
    return PlanPeriod(start=start, days=min((end - start).days + 1, MAX_PLAN_DAYS))


def default_period(today: date) -> PlanPeriod:
    """What a plan covers when nobody picked: the month in progress."""
    return month_period(today)


def requested_period(start: date, days: int | None = None) -> PlanPeriod:
    """A period the person picked: ``days`` from ``start`` (the Plan tab's
    week, two weeks, 30 days), or the month from ``start`` without a length."""
    if days is None:
        return month_period(start)
    if not 1 <= days <= MAX_PLAN_DAYS:
        raise ValueError(f"A plan covers 1 to {MAX_PLAN_DAYS} days, not {days}.")
    return PlanPeriod(start=start, days=days)


def keep_drafted_days(old_days: list, new_days: list) -> tuple[list, list[int]]:
    """A revision of a plan whose posts are partly drafted. A day with a post
    (``post_id``) is the draft's slot: the board finds the post through it,
    and rewriting its topic would leave a draft about something the plan no
    longer says. So that day stays as it was, and its index is reported.
    Every other day takes the revision."""
    merged = list(new_days)
    kept: list[int] = []
    for i, old in enumerate(old_days[: len(merged)]):
        if isinstance(old, dict) and old.get("post_id"):
            merged[i] = old
            kept.append(i)
    return merged, kept
