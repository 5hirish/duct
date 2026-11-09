"""Where a plan's posts go, channel by channel, and what each channel's own
history says to make there.

The plan used to read one history for the whole account: TikTok, Instagram
and YouTube ranked together, the text channels left out, and every post
judged on completion and saves whatever the brand posted for. Three things
changed, all here in code, so the plan prompt only reads the answers:

* **A goal measure.** The brand's content goal decides what "earned" means:
  people reached, a conversation started, or intent (saves and shares, the
  closest step to a signup these numbers have; conversions themselves are
  not measured anywhere yet).
* **Each channel on its own history.** Its post types, pillars, hooks and
  best and weakest posts, ranked on that measure, so a LinkedIn plan is never
  steered by a TikTok's numbers.
* **Effort moves slowly.** A channel's share of the plan's days starts from
  the last plan's and moves toward the channels that return more of the goal
  per post: at most a quarter in one plan, never below a post a week, and
  only once two channels have enough measured posts to compare. A day counts
  for the channel listed first in its platforms, the one it is made for.

No network and no model call, like ``performance.py``: the runner calls
:func:`load_channel_mix` off the event loop.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from statistics import median
from uuid import UUID

from agents.content.channels import primary_channel, resolve
from agents.content.performance import (
    ENGAGEMENT,
    INTENT,
    LOOKBACK_POSTS,
    MIN_MEASURED_POSTS,
    REACHED,
    AccountPerformance,
    Measure,
    PostSample,
    measure,
    planned_bets,
    summarise,
)
from agents.content.schema import POST_TYPES, TEXT_POST_TYPE, VISUAL_POST_TYPES

# One plan moves a channel's share of the days by at most this fraction of
# itself, and closes this much of the gap its numbers point to. "Slowly":
# a channel that returns twice the goal per post gains a quarter, not double,
# and a bad month costs a quarter, not the channel.
MAX_SHIFT = 0.25
PULL = 0.5
# Within this band of the middle channel a channel holds its share.
HOLD_BAND = 0.15
# Every active channel keeps a post a week, so the one that trails today is
# still tested tomorrow.
FLOOR_DAYS_PER_WEEK = 1
# How many recent published posts are read across all channels before each
# channel keeps its own last LOOKBACK_POSTS.
_READ_POSTS = 240


class GoalKind(StrEnum):
    REACH = "reach"
    ENGAGEMENT = "engagement"
    INTENT = "intent"


@dataclass(frozen=True)
class Goal:
    """What a post is judged on, and the brand's words it was read from."""

    kind: GoalKind
    source: str = ""

    @property
    def measure(self) -> str:
        """The performance metric that counts this goal per post."""
        return _MEASURE[self.kind]

    @property
    def ladder(self) -> tuple[str, ...]:
        """The ranking signals to try within a channel, the goal's own first."""
        return _LADDER[self.kind]


_MEASURE = {GoalKind.REACH: REACHED, GoalKind.ENGAGEMENT: ENGAGEMENT, GoalKind.INTENT: INTENT}
_LADDER = {
    GoalKind.REACH: (REACHED, "shares"),
    GoalKind.ENGAGEMENT: (ENGAGEMENT, "completion_rate"),
    GoalKind.INTENT: (INTENT, "completion_rate"),
}

# Read off the brand's own words. A business outcome beats attention: "reach
# people and get signups" is a signup goal. Nothing said is intent too, since
# every north-star option a project can pick (leads, revenue, active users,
# bookings) is a business outcome.
_GOAL_WORDS: tuple[tuple[GoalKind, tuple[str, ...]], ...] = (
    (GoalKind.INTENT, (
        "lead", "signup", "sign up", "sign-up", "sale", "sell", "revenue", "download", "install",
        "trial", "booking", "book a", "demo", "convert", "conversion", "customer", "purchase",
        "waitlist", "subscribe", "subscriber", "users", "pipeline",
    )),
    (GoalKind.ENGAGEMENT, ("engagement", "engage", "community", "comment", "conversation", "loyal")),
    (GoalKind.REACH, ("awareness", "reach", "follower", "visibility", "impression", "views", "audience", "known")),
)


def goal_from(*texts: str) -> Goal:
    """The goal the brand's words name, first match by precedence; intent
    when they name none."""
    words = " ".join(t for t in texts if t).strip()
    lowered = words.lower()
    for kind, needles in _GOAL_WORDS:
        if any(re.search(rf"\b{re.escape(n)}", lowered) for n in needles):
            return Goal(kind, words)
    return Goal(GoalKind.INTENT, words)


# A channel's standing against the middle channel on the goal per post.
LEADS = "leads"
HOLDS = "holds"
TRAILS = "trails"
UNTESTED = "untested"


@dataclass(frozen=True)
class ChannelReport:
    """One channel: its history, what it returns per post, its days."""

    channel: str
    performance: AccountPerformance
    goal_per_post: Measure
    days: int
    last_days: int | None
    standing: str


@dataclass(frozen=True)
class ChannelMix:
    """The per-channel picture the plan turn reads."""

    goal: Goal
    days: int
    last_plan_days: int
    floor: int
    channels: list[ChannelReport] = field(default_factory=list)

    @property
    def has_history(self) -> bool:
        return any(c.performance.has_history for c in self.channels)


def floor_days(days: int, channels: int) -> int:
    """Days every channel keeps: a post a week, cut back when the plan is too
    short to give every channel that many."""
    if channels <= 0 or days <= 0:
        return 0
    floor = max(1, days // 7 * FLOOR_DAYS_PER_WEEK)
    return floor if floor * channels <= days else days // channels


def allocate(
    channels: list[str], days: int, last: dict[str, int], yields: dict[str, float | None],
) -> tuple[dict[str, int], dict[str, str]]:
    """Each channel's days in a plan of ``days``, and its standing.

    ``last`` is the days the last plan gave each channel (empty with no last
    plan: an even start); ``yields`` the median goal per post, None where too
    few posts measured it to judge. Returns counts that sum to ``days``.
    """
    if not channels or days <= 0:
        return {}, {}
    total_last = sum(last.get(c, 0) for c in channels)
    share = {c: (last.get(c, 0) / total_last) if total_last else 1 / len(channels) for c in channels}

    measured = {c: y for c in channels if (y := yields.get(c)) is not None}
    middle = median(measured.values()) if len(measured) >= 2 else None
    weight: dict[str, float] = {}
    standing: dict[str, str] = {}
    for c in channels:
        y = measured.get(c)
        if y is None:
            weight[c], standing[c] = share[c], UNTESTED
            continue
        if middle is None:
            weight[c], standing[c] = share[c], HOLDS
            continue
        ratio = y / middle if middle > 0 else (2.0 if y > 0 else 1.0)
        step = min(1 + MAX_SHIFT, max(1 - MAX_SHIFT, 1 + PULL * (ratio - 1)))
        weight[c] = share[c] * step
        standing[c] = LEADS if ratio >= 1 + HOLD_BAND else TRAILS if ratio <= 1 - HOLD_BAND else HOLDS

    floor = floor_days(days, len(channels))
    counts = {c: floor for c in channels}
    spare = days - floor * len(channels)
    total_weight = sum(weight.values())
    wanted = {
        c: max(0.0, (weight[c] / total_weight if total_weight else 1 / len(channels)) * days - floor)
        for c in channels
    }
    total_wanted = sum(wanted.values())
    if spare > 0:
        quota = {c: (wanted[c] / total_wanted if total_wanted else 1 / len(channels)) * spare for c in channels}
        for c in channels:
            counts[c] += int(quota[c])
        left = days - sum(counts.values())
        # Largest remainder first; the channel order breaks a tie, so the
        # answer is the same every run.
        for c in sorted(channels, key=lambda c: (-(quota[c] - int(quota[c])), channels.index(c)))[:left]:
            counts[c] += 1
    return counts, standing


def _days_by_channel(plan_days: list) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for day in plan_days or []:
        if isinstance(day, dict):
            counts[primary_channel(day.get("platforms"))] += 1
    return dict(counts)


def build_mix(
    samples: list[PostSample], channels: list[str], goal: Goal, days: int, last_plan: list | None,
) -> ChannelMix:
    """The mix from published posts (newest first), the brand's channels, the
    plan's length and the last plan's days. Posts on a channel the brand no
    longer posts on are left out. A brand that has not said where it posts is
    planned on the channels its posts went to, else the default one, as the
    plan prompt assumes; it must not lose its history for saying nothing."""
    wanted = [c for c in dict.fromkeys(channels) if c]
    if not wanted:
        wanted = list(dict.fromkeys(s.channel for s in samples if s.channel)) or [primary_channel(None)]
    by_channel: dict[str, list[PostSample]] = defaultdict(list)
    for s in samples:
        if s.channel in wanted and len(by_channel[s.channel]) < LOOKBACK_POSTS:
            by_channel[s.channel].append(s)

    last = _days_by_channel(last_plan or [])
    perf: dict[str, AccountPerformance] = {}
    per_post: dict[str, Measure] = {}
    for c in wanted:
        known = (TEXT_POST_TYPE,) if resolve(c).text_first else VISUAL_POST_TYPES
        perf[c] = summarise(by_channel[c], ladder=goal.ladder, known_types=known)
        per_post[c] = measure(by_channel[c], goal.measure)
    yields = {c: m.median if m.measured >= MIN_MEASURED_POSTS else None for c, m in per_post.items()}
    counts, standing = allocate(wanted, days, last, yields)
    return ChannelMix(
        goal=goal,
        days=days,
        last_plan_days=len(last_plan or []),
        floor=floor_days(days, len(wanted)),
        channels=[
            ChannelReport(
                channel=c,
                performance=perf[c],
                goal_per_post=per_post[c],
                days=counts.get(c, 0),
                last_days=last.get(c) if last_plan else None,
                standing=standing.get(c, UNTESTED),
            )
            for c in wanted
        ],
    )


def load_channel_mix(project_id: UUID, channels: list[str], goal: Goal, days: int) -> ChannelMix:
    """Read the project's published posts and plans, and build the mix.

    Synchronous, a few queries, so the runner calls it off the event loop.
    Raises when the database is unreachable: "no history" is a claim about
    the account, and a dead connection must not be allowed to make it.
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
            .limit(_READ_POSTS)
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
                channel=primary_channel(post.platforms),
                pillar=post.pillar or "",
                topic=post.topic or "",
            )
            for post in posts
        ]
        last_plan = next((list(p.days) for p in reversed(plans) if p.days), None)
    return build_mix(samples, channels, goal, days, last_plan)


__all__ = [
    "ChannelMix",
    "ChannelReport",
    "Goal",
    "GoalKind",
    "allocate",
    "build_mix",
    "floor_days",
    "goal_from",
    "load_channel_mix",
]
