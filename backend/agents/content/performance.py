"""What an account's own posting history says, for the next content plan.

Four signals, computed from what is already stored — each post's ``perf`` and
the plans that produced the posts — with no network and no model call:

* **Type ranking.** Slideshow, video and image ranked on how people watched
  and kept them (completion, then saves, then shares), never on likes: a post
  a thousand people finished beats one ten thousand people tapped past.
* **Explore / exploit.** The proven leader is the type to scale; the untested
  and the too-thin-to-judge are the ones a plan must keep testing, because a
  type that is never planned never earns the history to be planned.
* **Graded bets.** The hook, funnel stage and objective each planned post was
  a bet on, scored by the same signal, so a plan learns strategy and not only
  format.
* **Best posting times.** Hour of day and weekday, ranked by this account's
  own median views rather than a generic chart.

A metric that was never recorded is **unknown, not zero**. PostBridge syncs
views, likes, comments and shares; completion and saves arrive only when
someone logs them. Reading an absent completion rate as 0% would crown
whichever type happened to have one logged, so every median here is taken
over the posts that carry the metric, with that count beside it.

Plain Python on purpose: the runner calls :func:`load_account_performance`
off the event loop and hands the result to the prompt builder, which renders
it into the plan run's user turn.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from uuid import UUID

# Read off the plan schema, so a new type is "untested" the moment Day accepts it.
from agents.content.schema import POST_TYPES

# How many recent posts inform a plan. Recent, because an account's audience
# and the platform both move; a year-old winner is weak evidence for next month.
LOOKBACK_POSTS = 40

# Below this many measured posts a median is an anecdote: the type or bet is
# "unproven" — worth testing, not yet worth scaling.
MIN_MEASURED_POSTS = 3

# Posting times need a few posts with views before any window means anything,
# and a window needs two posts, or one viral post names "the best hour".
MIN_TIMED_POSTS = 5
MIN_WINDOW_POSTS = 2
TOP_WINDOWS = 3

# Graded bets per dimension shown to the model. More is noise in the prompt.
TOP_BETS = 5

# Ranking signals, strongest first. Completion and saves say a post was watched
# and kept; shares is the member of that family PostBridge syncs by itself, so
# an account that never logs metrics by hand still gets a ranking. Likes are
# deliberately absent.
RANKING_SIGNALS: tuple[str, ...] = ("completion_rate", "saves", "shares")
VIEWS = "views"

# The plan-day fields a planned post is graded on. Named once: the loader reads
# them off stored plan days and the grader buckets by them.
BET_DIMENSIONS: tuple[str, ...] = ("hook_type", "funnel_stage", "objective")
_BET_VALUE_CHARS = 40

WEEKDAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Verdicts on a post type.
PROVEN = "proven"
UNPROVEN = "unproven"
UNTESTED = "untested"


# ---------------------------------------------------------------------------
# Reading a metric
# ---------------------------------------------------------------------------

# ``perf`` holds three key conventions: PostBridge's ``*_count`` fields, the
# Perf schema's own names, and whatever a hand-logged snapshot sent. Each
# metric is read through its aliases in priority order.
_METRIC_KEYS: dict[str, tuple[str, ...]] = {
    VIEWS: ("view_count", "play_count", "views"),
    "saves": ("save_count", "collect_count", "saves"),
    "shares": ("share_count", "shares"),
    "completion_rate": ("completion_rate", "completionRate", "watched_full_video", "watchFullVideo"),
}


def read_metric(perf: object, name: str) -> float | None:
    """One metric from a post's ``perf``, or None when it was never recorded.

    The only place this module reads ``perf``. When the shared alias contract
    (``METRIC_ALIASES``) lands in ``service/content_metrics.py``, this body
    becomes a call to it and nothing else here changes.

    A completion rate above 1 is a percentage — the app's manual form records
    0-100, the Perf schema 0-1 — and is scaled so the two compare.
    """
    if not isinstance(perf, dict):
        return None
    for key in _METRIC_KEYS.get(name, (name,)):
        value = perf.get(key)
        # bool is an int to Python and never a metric.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(value):
            continue
        if name == "completion_rate" and value > 1:
            value = value / 100
        return float(value)
    return None


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostSample:
    """One published post, as much as the signals need of it.

    ``bet`` is what the plan day that produced it chose — ``{hook_type,
    funnel_stage, objective}`` — and empty for a post nobody planned.
    """

    post_type: str
    perf: dict
    posted_at: datetime | None = None
    hook_type: str = ""
    bet: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Measure:
    """A median over the posts that carry the metric, and how many do."""

    median: float | None
    measured: int


@dataclass(frozen=True)
class GroupStats:
    """One content type or one bet, summarised on every ranking signal."""

    key: str
    posts: int
    measures: dict[str, Measure]
    verdict: str = ""

    def score(self, signal: str | None) -> float | None:
        return self.measures[signal].median if signal else None

    def measured(self, signal: str | None) -> int:
        return self.measures[signal].measured if signal else 0


@dataclass(frozen=True)
class Window:
    """A posting window — an hour of day or a weekday, in UTC."""

    label: str
    posts: int
    median_views: float


@dataclass(frozen=True)
class AccountPerformance:
    """Everything the plan prompt says about the account's history."""

    posts: int
    ranked_by: str | None = None
    types: list[GroupStats] = field(default_factory=list)
    exploit: str | None = None
    explore: list[str] = field(default_factory=list)
    bets: dict[str, list[GroupStats]] = field(default_factory=dict)
    hours_utc: list[Window] = field(default_factory=list)
    weekdays: list[Window] = field(default_factory=list)
    timed_posts: int = 0

    @property
    def has_history(self) -> bool:
        return self.posts > 0


# ---------------------------------------------------------------------------
# The signals
# ---------------------------------------------------------------------------


def _measure(samples: list[PostSample], metric: str) -> Measure:
    values = [v for s in samples if (v := read_metric(s.perf, metric)) is not None]
    return Measure(median=median(values) if values else None, measured=len(values))


def _group(key: str, samples: list[PostSample], verdict: str = "") -> GroupStats:
    return GroupStats(
        key=key,
        posts=len(samples),
        measures={m: _measure(samples, m) for m in (*RANKING_SIGNALS, VIEWS)},
        verdict=verdict,
    )


def _by_type(samples: list[PostSample]) -> dict[str, list[PostSample]]:
    by_type: dict[str, list[PostSample]] = defaultdict(list)
    for s in samples:
        by_type[s.post_type].append(s)
    return by_type


def ranking_signal(samples: list[PostSample]) -> str | None:
    """The strongest signal enough posts carry to rank on, or None.

    One signal for the whole comparison, so every type is judged on the same
    ruler: a slideshow's saves are never weighed against a video's completion.
    """
    groups = _by_type(samples).values()
    for signal in RANKING_SIGNALS:
        if any(_measure(group, signal).measured >= MIN_MEASURED_POSTS for group in groups):
            return signal
    return None


def _ranked(groups: list[GroupStats], signal: str | None) -> list[GroupStats]:
    """Best score first; unknown scores after every known one, then by volume."""
    def key(g: GroupStats) -> tuple:
        score = g.score(signal)
        return (score is None, -(score or 0.0), -g.measured(signal), -g.posts, g.key)

    return sorted(groups, key=key)


def rank_types(samples: list[PostSample], signal: str | None) -> tuple[list[GroupStats], str | None, list[str]]:
    """Every post type with a verdict, the one to exploit, and those to explore.

    Proven types lead, best first; then unproven ones; then the untested.
    Explore lists the untested before the unproven — no data at all is the
    bigger blind spot than thin data.
    """
    by_type = _by_type(samples)
    proven, unproven = [], []
    for post_type, group in by_type.items():
        enough = signal is not None and _measure(group, signal).measured >= MIN_MEASURED_POSTS
        (proven if enough else unproven).append(_group(post_type, group, PROVEN if enough else UNPROVEN))
    untested = [_group(t, [], UNTESTED) for t in POST_TYPES if t not in by_type]

    proven = _ranked(proven, signal)
    unproven = _ranked(unproven, signal)
    exploit = proven[0].key if proven else None
    explore = [g.key for g in untested] + [g.key for g in unproven]
    return proven + unproven + untested, exploit, explore


def _bet_value(sample: PostSample, dimension: str) -> str:
    """The bet a post made on one dimension, normalised for bucketing.

    The hook as published wins over the hook planned: the audience reacted to
    the post, and a post drafted outside any plan still has one. Funnel stage
    and objective exist only on the plan.
    """
    raw = sample.hook_type if dimension == "hook_type" and sample.hook_type else sample.bet.get(dimension)
    return str(raw or "").strip().lower()[:_BET_VALUE_CHARS]


def grade_bets(samples: list[PostSample], signal: str | None) -> dict[str, list[GroupStats]]:
    """Per bet dimension, each value's record on the ranking signal, best first."""
    graded: dict[str, list[GroupStats]] = {}
    for dimension in BET_DIMENSIONS:
        buckets: dict[str, list[PostSample]] = defaultdict(list)
        for s in samples:
            value = _bet_value(s, dimension)
            if value:
                buckets[value].append(s)
        groups = [_group(value, group) for value, group in buckets.items()]
        graded[dimension] = _ranked(groups, signal)[:TOP_BETS]
    return graded


def _windows(buckets: dict[str, list[float]]) -> list[Window]:
    windows = [
        Window(label=label, posts=len(views), median_views=median(views))
        for label, views in buckets.items()
        if len(views) >= MIN_WINDOW_POSTS
    ]
    windows.sort(key=lambda w: (-w.median_views, -w.posts, w.label))
    return windows[:TOP_WINDOWS]


def best_posting_times(samples: list[PostSample]) -> tuple[list[Window], list[Window], int]:
    """The best hours of day and weekdays by median views, in UTC.

    Hour and weekday are ranked apart rather than as (weekday, hour) pairs:
    forty posts over 168 pairs leaves nearly every pair with one post, and one
    post is an anecdote. Returns ``(hours, weekdays, posts_with_views)``; both
    lists are empty until the account has enough timed posts to say anything.
    """
    timed = [
        (s.posted_at, views)
        for s in samples
        if s.posted_at is not None and (views := read_metric(s.perf, VIEWS)) is not None
    ]
    if len(timed) < MIN_TIMED_POSTS:
        return [], [], len(timed)
    hours: dict[str, list[float]] = defaultdict(list)
    days: dict[str, list[float]] = defaultdict(list)
    for posted_at, views in timed:
        hours[f"{posted_at.hour:02d}:00"].append(views)
        days[WEEKDAYS[posted_at.weekday()]].append(views)
    return _windows(hours), _windows(days), len(timed)


def summarise(samples: list[PostSample]) -> AccountPerformance:
    """All four signals from a list of published posts (newest first)."""
    if not samples:
        return AccountPerformance(posts=0, explore=list(POST_TYPES))
    signal = ranking_signal(samples)
    types, exploit, explore = rank_types(samples, signal)
    hours, weekdays, timed = best_posting_times(samples)
    return AccountPerformance(
        posts=len(samples),
        ranked_by=signal,
        types=types,
        exploit=exploit,
        explore=explore,
        bets=grade_bets(samples, signal),
        hours_utc=hours,
        weekdays=weekdays,
        timed_posts=timed,
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def planned_bets(plan_days: list[list]) -> dict[str, dict]:
    """``post_id → {hook_type, funnel_stage, objective}`` from stored plan days.

    A day links to the post drafted from it by ``post_id``. Every plan the
    project has counts, so a bet survives the plan being replaced; a post
    planned twice keeps the bet of the last plan passed in.
    """
    bets: dict[str, dict] = {}
    for days in plan_days:
        for day in days or []:
            if not isinstance(day, dict) or not day.get("post_id"):
                continue
            bets[str(day["post_id"])] = {d: day.get(d) or "" for d in BET_DIMENSIONS}
    return bets


def load_account_performance(project_id: UUID) -> AccountPerformance:
    """Read the project's recent published posts and its plans, and summarise.

    Synchronous — two queries — so the runner calls it off the event loop.
    Raises when the database is unreachable: "no history" is a claim about the
    account, and a dead connection must not be allowed to make it.
    """
    from sqlmodel import Session, select

    from db.session import get_engine
    from models.content import ContentPlan, ContentPost

    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    with Session(engine) as db:
        posts = db.exec(
            select(ContentPost)
            .where(ContentPost.project_id == project_id)
            .where(ContentPost.posted_at.is_not(None))  # type: ignore[union-attr]
            .order_by(ContentPost.posted_at.desc())  # type: ignore[union-attr]
            .limit(LOOKBACK_POSTS)
        ).all()
        plans = db.exec(
            select(ContentPlan)
            .where(ContentPlan.project_id == project_id)
            .order_by(ContentPlan.created_at)
        ).all()
        bets = planned_bets([plan.days for plan in plans])
        samples = [
            PostSample(
                post_type=post.post_type or POST_TYPES[0],
                perf=post.perf or {},
                posted_at=post.posted_at,
                hook_type=post.hook_type or "",
                bet=bets.get(str(post.id), {}),
            )
            for post in posts
        ]
    return summarise(samples)


__all__ = [
    "AccountPerformance",
    "GroupStats",
    "Measure",
    "POST_TYPES",
    "PostSample",
    "Window",
    "best_posting_times",
    "grade_bets",
    "load_account_performance",
    "planned_bets",
    "rank_types",
    "ranking_signal",
    "read_metric",
    "summarise",
]
