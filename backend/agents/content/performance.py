"""What an account's own posting history says, for the next content plan.

Four signals, computed from what is already stored — each post's ``perf`` and
the plans that produced the posts — with no network and no model call:

* **Type ranking.** Slideshow, video and image ranked on how people watched
  and kept them (completion, then saves, then shares), never on likes: a post
  a thousand people finished beats one ten thousand people tapped past.
* **Explore / exploit.** The proven leader is the type to scale; the untested
  and the too-thin-to-judge are the ones a plan must keep testing, because a
  type that is never planned never earns the history to be planned. Proven
  means enough posts measured *and* something earned: three videos with no
  saves or shares between them are measured, and flat, not a type to scale.
* **Graded bets.** The hook, funnel stage and objective each planned post was
  a bet on, scored by the same signal, so a plan learns strategy and not only
  format.
* **Best posting times.** Hour of day and weekday, ranked by this account's
  own median views rather than a generic chart.

A metric that was never recorded is **unknown, not zero**. A scheduler syncs
views, likes, comments and shares; completion and saves arrive only when
someone logs them. Reading an absent completion rate as 0% would crown
whichever type happened to have one logged, so every median here is taken
over the posts that carry the metric, with that count beside it.

Plain Python on purpose. ``channel_mix.py`` reads the posts and runs
:func:`summarise` once per channel, on the ladder the brand's goal picks; the
prompt builder renders the result into the plan run's user turn.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median

# Read off the plan schema, so a new type is "untested" the moment Day accepts it.
from agents.content.schema import POST_TYPES, VISUAL_POST_TYPES
from service.content_metrics import METRIC_ALIASES, metric_value

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
# and kept; shares is the member of that family every scheduler syncs, so
# an account that never logs metrics by hand still gets a ranking. Likes are
# deliberately absent.
RANKING_SIGNALS: tuple[str, ...] = ("completion_rate", "saves", "shares")
VIEWS = "views"

# Goal measures: one number per post for "did this post do what the brand
# posts for". A sum counts the people who acted (a save and a share are two
# actions); a first-of takes the one reading a channel reports. Counts, not
# rates, because effort is a post: what a channel returns per post is the
# number that decides where the next posts go.
INTENT = "intent"          # saves + shares: kept it, sent it, the step before a signup
ENGAGEMENT = "engagement"  # comments + shares + saves: a conversation started
REACHED = "reached"        # reach, else views: people the post got in front of
COMPOSITE_SUMS: dict[str, tuple[str, ...]] = {
    INTENT: ("saves", "shares"),
    ENGAGEMENT: ("comments", "shares", "saves"),
}
COMPOSITE_FIRST: dict[str, tuple[str, ...]] = {
    REACHED: ("reach", "views"),
}

# The plan-day fields a planned post is graded on. Named once: the loader reads
# them off stored plan days and the grader buckets by them.
BET_DIMENSIONS: tuple[str, ...] = ("hook_type", "funnel_stage", "objective")
# What a plan is graded on: the pillar a post was about, then the bets.
PILLAR = "pillar"
GRADED_DIMENSIONS: tuple[str, ...] = (PILLAR, *BET_DIMENSIONS)
# Posts named as the best and weakest of a channel: topics to build on, and
# ones not to repeat as they were.
TOP_STANDOUTS = 2
_BET_VALUE_CHARS = 40

WEEKDAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Verdicts on a post type or a bet. Unproven is too few posts measured to
# say: a hint. Flat is enough measured and nothing earned. Only proven is
# evidence to scale; on 2026-11-08 a plan put 14 of 23 days on video for
# three posts with 0 saves, and 9 days on one hook a single post had tried.
PROVEN = "proven"
UNPROVEN = "unproven"
FLAT = "flat"
UNTESTED = "untested"


# ---------------------------------------------------------------------------
# Reading a metric
# ---------------------------------------------------------------------------


def read_metric(perf: object, name: str) -> float | None:
    """One metric from a post's ``perf``, or None when it was never recorded.

    The only place this module reads ``perf``. Which keys mean which metric,
    and which wins when a sync and a person both wrote one, is
    ``service/content_metrics.py``'s contract; this adds only what a median
    needs on top: a non-finite number is no reading, and a completion rate
    is a fraction here — the contract stores 0-100, older snapshots sent 0-1,
    so anything above 1 is scaled.
    """
    if not isinstance(perf, dict):
        return None
    if name in COMPOSITE_SUMS:
        # Unknown, not zero, when none of the parts was recorded; the parts a
        # channel does report are summed (X has no saves, so its intent is
        # its shares).
        parts = [v for part in COMPOSITE_SUMS[name] if (v := read_metric(perf, part)) is not None]
        return float(sum(parts)) if parts else None
    if name in COMPOSITE_FIRST:
        return next((v for part in COMPOSITE_FIRST[name] if (v := read_metric(perf, part)) is not None), None)
    if name not in METRIC_ALIASES:
        return None
    value = metric_value(perf, name)
    if value is None or not math.isfinite(value):
        return None
    if name == "completion_rate" and value > 1:
        value = value / 100
    return float(value)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostSample:
    """One published post, as much as the signals need of it.

    ``bet`` is what the plan day that produced it chose — ``{hook_type,
    funnel_stage, objective}`` — and empty for a post nobody planned.
    ``channel`` is the platform it was made for (its first), ``pillar`` and
    ``topic`` what it was about.
    """

    post_type: str
    perf: dict
    posted_at: datetime | None = None
    hook_type: str = ""
    bet: dict = field(default_factory=dict)
    channel: str = ""
    pillar: str = ""
    topic: str = ""


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
class Standout:
    """One post that did best or worst on the ranking signal."""

    topic: str
    pillar: str
    score: float


@dataclass(frozen=True)
class AccountPerformance:
    """Everything the plan prompt says about the account's history, or about
    one channel's (``summarise`` runs on either)."""

    posts: int
    ranked_by: str | None = None
    types: list[GroupStats] = field(default_factory=list)
    exploit: str | None = None
    explore: list[str] = field(default_factory=list)
    bets: dict[str, list[GroupStats]] = field(default_factory=dict)
    hours_utc: list[Window] = field(default_factory=list)
    weekdays: list[Window] = field(default_factory=list)
    timed_posts: int = 0
    # The metrics each group carries, in the order the block prints them.
    metrics: tuple[str, ...] = (*RANKING_SIGNALS, VIEWS)
    best: list[Standout] = field(default_factory=list)
    weakest: list[Standout] = field(default_factory=list)

    @property
    def has_history(self) -> bool:
        return self.posts > 0


# ---------------------------------------------------------------------------
# The signals
# ---------------------------------------------------------------------------


def measure(samples: list[PostSample], metric: str) -> Measure:
    """The median of ``metric`` over the posts that carry it, and how many do."""
    values = [v for s in samples if (v := read_metric(s.perf, metric)) is not None]
    return Measure(median=median(values) if values else None, measured=len(values))


def _group(
    key: str, samples: list[PostSample], verdict: str = "",
    metrics: tuple[str, ...] = (*RANKING_SIGNALS, VIEWS),
) -> GroupStats:
    return GroupStats(
        key=key,
        posts=len(samples),
        measures={m: measure(samples, m) for m in metrics},
        verdict=verdict,
    )


def _shown(ladder: tuple[str, ...]) -> tuple[str, ...]:
    """The ladder's metrics and views, each once, in that order."""
    return tuple(dict.fromkeys((*ladder, VIEWS)))


def _by_type(samples: list[PostSample]) -> dict[str, list[PostSample]]:
    by_type: dict[str, list[PostSample]] = defaultdict(list)
    for s in samples:
        by_type[s.post_type].append(s)
    return by_type


def ranking_signal(samples: list[PostSample], ladder: tuple[str, ...] = RANKING_SIGNALS) -> str | None:
    """The strongest signal enough posts carry to rank on, or None.

    One signal for the whole comparison, so every type is judged on the same
    ruler: a slideshow's saves are never weighed against a video's completion.
    ``ladder`` is the order to try them in: the brand's goal decides it
    (``agents/content/channel_mix.py``), the default is the watched-and-kept one.
    """
    groups = _by_type(samples).values()
    for signal in ladder:
        if any(measure(group, signal).measured >= MIN_MEASURED_POSTS for group in groups):
            return signal
    return None


def verdict_on(samples: list[PostSample], signal: str | None) -> str:
    """Proven, flat or unproven: what ``samples`` say on ``signal``."""
    if signal is None:
        return UNPROVEN
    m = measure(samples, signal)
    if m.measured < MIN_MEASURED_POSTS:
        return UNPROVEN
    return PROVEN if (m.median or 0) > 0 else FLAT


def _ranked(groups: list[GroupStats], signal: str | None) -> list[GroupStats]:
    """Best score first; unknown scores after every known one, then by volume."""
    def key(g: GroupStats) -> tuple:
        score = g.score(signal)
        return (score is None, -(score or 0.0), -g.measured(signal), -g.posts, g.key)

    return sorted(groups, key=key)


def rank_types(
    samples: list[PostSample], signal: str | None,
    metrics: tuple[str, ...] = (*RANKING_SIGNALS, VIEWS),
    known_types: tuple[str, ...] = VISUAL_POST_TYPES,
) -> tuple[list[GroupStats], str | None, list[str]]:
    """Every post type with a verdict, the one to exploit, and those to explore.

    Proven types lead, best first; then unproven, flat, and the untested.
    Explore lists the untested first (no data at all is the bigger blind spot
    than thin data), then the unproven, then the flat: kept at the floor,
    since a type that earned nothing may have had the wrong posts, but never
    scaled.
    """
    by_type = _by_type(samples)
    sorted_by: dict[str, list[GroupStats]] = {PROVEN: [], UNPROVEN: [], FLAT: []}
    for post_type, group in by_type.items():
        verdict = verdict_on(group, signal)
        sorted_by[verdict].append(_group(post_type, group, verdict, metrics))
    untested = [_group(t, [], UNTESTED, metrics) for t in known_types if t not in by_type]

    proven, unproven, flat = (_ranked(sorted_by[v], signal) for v in (PROVEN, UNPROVEN, FLAT))
    exploit = proven[0].key if proven else None
    explore = [g.key for g in (*untested, *unproven, *flat)]
    return proven + unproven + flat + untested, exploit, explore


def _bet_value(sample: PostSample, dimension: str) -> str:
    """The bet a post made on one dimension, normalised for bucketing.

    The hook as published wins over the hook planned: the audience reacted to
    the post, and a post drafted outside any plan still has one. Funnel stage
    and objective exist only on the plan; the pillar only on the post.
    """
    if dimension == PILLAR:
        return bet_key(sample.pillar)
    raw = sample.hook_type if dimension == "hook_type" and sample.hook_type else sample.bet.get(dimension)
    return bet_key(raw)


def bet_key(raw: object) -> str:
    """A bet's value as it is bucketed and graded, so a planned day can be
    matched to its record."""
    return str(raw or "").strip().lower()[:_BET_VALUE_CHARS]


def grade_bets(
    samples: list[PostSample], signal: str | None,
    metrics: tuple[str, ...] = (*RANKING_SIGNALS, VIEWS),
) -> dict[str, list[GroupStats]]:
    """Per graded dimension (the pillar and the plan's three bets), each
    value's record on the ranking signal, best first, with its verdict: a
    hook one post tried is a hint, never a strategy."""
    graded: dict[str, list[GroupStats]] = {}
    for dimension in GRADED_DIMENSIONS:
        buckets: dict[str, list[PostSample]] = defaultdict(list)
        for s in samples:
            value = _bet_value(s, dimension)
            if value:
                buckets[value].append(s)
        groups = [
            _group(value, group, verdict_on(group, signal), metrics=metrics) for value, group in buckets.items()
        ]
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


def standouts(samples: list[PostSample], signal: str | None) -> tuple[list[Standout], list[Standout]]:
    """The best and the weakest posts on ``signal`` that had a topic, or none
    while too few posts measured it to tell the ends apart."""
    scored = [
        Standout(topic=s.topic.strip(), pillar=s.pillar, score=v)
        for s in samples
        if signal and s.topic.strip() and (v := read_metric(s.perf, signal)) is not None
    ]
    if len(scored) < 2 * TOP_STANDOUTS:
        return [], []
    scored.sort(key=lambda x: -x.score)
    return scored[:TOP_STANDOUTS], scored[-TOP_STANDOUTS:][::-1]


def summarise(
    samples: list[PostSample], *,
    ladder: tuple[str, ...] = RANKING_SIGNALS,
    known_types: tuple[str, ...] = VISUAL_POST_TYPES,
) -> AccountPerformance:
    """All the signals from a list of published posts (newest first).

    ``ladder`` is the ranking signals to try, best first; ``known_types`` the
    types a post here could be (a text channel has one), so an untested one
    is named as such.
    """
    metrics = _shown(ladder)
    if not samples:
        return AccountPerformance(posts=0, explore=list(known_types), metrics=metrics)
    signal = ranking_signal(samples, ladder)
    types, exploit, explore = rank_types(samples, signal, metrics, known_types)
    hours, weekdays, timed = best_posting_times(samples)
    best, weakest = standouts(samples, signal)
    return AccountPerformance(
        posts=len(samples),
        ranked_by=signal,
        types=types,
        exploit=exploit,
        explore=explore,
        bets=grade_bets(samples, signal, metrics),
        hours_utc=hours,
        weekdays=weekdays,
        timed_posts=timed,
        metrics=metrics,
        best=best,
        weakest=weakest,
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


__all__ = [
    "FLAT",
    "PROVEN",
    "UNPROVEN",
    "UNTESTED",
    "AccountPerformance",
    "GroupStats",
    "Measure",
    "POST_TYPES",
    "PostSample",
    "Standout",
    "Window",
    "best_posting_times",
    "bet_key",
    "grade_bets",
    "measure",
    "planned_bets",
    "rank_types",
    "ranking_signal",
    "read_metric",
    "standouts",
    "summarise",
    "verdict_on",
]
