"""What happened to the plan so far — the review a planning session opens with.

Until 2026-11-08 a plan session's first turn wrote the next plan. The model
saw the account's type ranking (``performance.py``) and nothing else about the
plan it was replacing: ``history=[]`` was passed on every run, so the prompt
said "(no history)" beside a board holding thirty planned days. An expert does
it the other way round: what was planned, what went out, what did not and why,
what worked, what is coming up, and only then what to change. This module is
that reading, as data and as the ``<plan_review>`` block the prompt renders.

Two queries and no model call. A missing database raises (the caller degrades
to "could not be read", never to "nothing happened").
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from agents.content.plan_period import PlanPeriod, plan_end
from agents.content.plan_proposal import day_date
from service.content_metrics import metric_value

# How far back the review reads: this plan, the one before it. Older plans
# are history the performance block already summarises.
PLANS_TO_REVIEW = 2
# Posts listed by name in the review; the rest are counts.
TOP_POSTS = 3
UPCOMING_DAYS = 7
# A posted day is judged on these, in order; the first one recorded wins.
POSTED_SIGNALS = ("completion_rate", "saves", "shares", "views")


@dataclass
class DayState:
    index: int
    on: date | None
    topic: str
    pillar: str
    post_type: str
    platforms: list[str]
    state: str          # posted · scheduled · drafted · missed · upcoming · discarded · failed
    post_id: str | None = None
    hook_type: str = ""
    signal: str = ""     # "completion 41%" when the post recorded one
    signal_value: float | None = None


@dataclass
class PlanState:
    plan_id: UUID
    name: str
    start: date | None
    days: list[DayState]
    strategy: dict
    is_current: bool

    @property
    def counts(self) -> Counter:
        return Counter(d.state for d in self.days)

    @property
    def end(self) -> date | None:
        return plan_end(self.start, len(self.days))


@dataclass
class PlanReview:
    today: date
    period: PlanPeriod | None
    plans: list[PlanState] = field(default_factory=list)
    # Posted posts not tied to any reviewed plan (published outside a plan).
    unplanned_posted: int = 0
    platforms_posted: Counter = field(default_factory=Counter)

    @property
    def has_history(self) -> bool:
        return bool(self.plans) or self.unplanned_posted > 0

    @property
    def current(self) -> PlanState | None:
        return next((p for p in self.plans if p.is_current), None)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_plan_review(project_id: UUID, *, today: date, period: PlanPeriod | None = None) -> PlanReview:
    """Read the last plans and their posts; synchronous, two queries."""
    from sqlmodel import Session, select

    from db.session import get_engine
    from models.content import ContentPlan, ContentPost

    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    with Session(engine) as db:
        plans = [
            p for p in db.exec(
                select(ContentPlan)
                .where(ContentPlan.project_id == project_id)
                .order_by(ContentPlan.created_at.desc())
            ).all()
            if p.days
        ][:PLANS_TO_REVIEW]
        posts = db.exec(
            select(ContentPost)
            .where(ContentPost.project_id == project_id)
            .where(ContentPost.status != "pending")
            .order_by(ContentPost.updated_at.desc())  # type: ignore[union-attr]
            .limit(200)
        ).all()
        by_id = {str(p.id): p for p in posts}
        review = PlanReview(today=today, period=period)
        covered: set[str] = set()
        for plan in plans:
            is_current = bool(
                plan.start_date
                and plan.start_date <= today <= (plan_end(plan.start_date, len(plan.days)) or today)
            )
            days = [
                _day_state(i, raw, plan.start_date, today, by_id)
                for i, raw in enumerate(plan.days)
                if isinstance(raw, dict)
            ]
            covered.update(d.post_id for d in days if d.post_id)
            review.plans.append(PlanState(
                plan_id=plan.id, name=plan.name, start=plan.start_date, days=days,
                strategy=plan.strategy or {}, is_current=is_current,
            ))
        for post in posts:
            if post.posted_at and str(post.id) not in covered:
                review.unplanned_posted += 1
            if post.posted_at:
                for platform in post.platforms or []:
                    review.platforms_posted[str(platform)] += 1
        return review


def _day_state(index: int, raw: dict, start: date | None, today: date, by_id: dict) -> DayState:
    on = day_date(start, index)
    post = by_id.get(str(raw.get("post_id") or ""))
    state = "upcoming"
    signal, value = "", None
    if post is not None:
        status = str(post.status or "")
        if post.posted_at or status == "posted":
            state = "posted"
            signal, value = _best_signal(post.perf or {})
        elif post.scheduled_at or status == "scheduled":
            state = "scheduled"
        elif status in ("discarded", "failed"):
            state = status
        else:
            state = "drafted"
    elif raw.get("status") == "discarded":
        state = "discarded"
    if state in ("upcoming", "drafted") and on is not None and on < today:
        state = "missed"
    return DayState(
        index=index, on=on,
        topic=str(raw.get("topic") or ""), pillar=str(raw.get("pillar") or ""),
        post_type=str(raw.get("post_type") or "slideshow"),
        platforms=[str(p) for p in (raw.get("platforms") or [])],
        state=state, post_id=str(post.id) if post is not None else None,
        hook_type=str(raw.get("hook_type") or (post.hook_type if post is not None else "") or ""),
        signal=signal, signal_value=value,
    )


def _best_signal(perf: dict) -> tuple[str, float | None]:
    for key in POSTED_SIGNALS:
        value = metric_value(perf, key)
        if value is None:
            continue
        if key == "completion_rate":
            return f"completion {value:.0%}" if value <= 1 else f"completion {value:.0f}%", float(value)
        return f"{key} {int(value):,}", float(value)
    return "", None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_plan_review(review: PlanReview | None) -> str:
    """The ``<plan_review>`` block for the opening turn. Says in words what it
    could not read, so the model never takes an outage for an empty account."""
    if review is None:
        return _block(["  The plan history could not be read this run. Say so, and review", "  from <account_performance> alone."])
    if not review.has_history:
        return _block(["  No plan and no published post yet: nothing to review."])

    lines: list[str] = [f"  today: {review.today.isoformat()}"]
    if review.period:
        lines.append(f"  period under review: {review.period.start.isoformat()} to {review.period.end.isoformat()}")
    for plan in review.plans:
        lines += _plan_lines(plan, review.today)
    if review.unplanned_posted:
        lines.append(f"  posted outside any plan: {review.unplanned_posted} posts")
    if review.platforms_posted:
        split = ", ".join(f"{k} {v}" for k, v in review.platforms_posted.most_common())
        lines.append(f"  published posts by platform: {split}")
    return _block(lines)


def _plan_lines(plan: PlanState, today: date) -> list[str]:
    counts = plan.counts
    span = f"{plan.start.isoformat()} to {plan.end.isoformat()}" if plan.start and plan.end else f"{len(plan.days)} days"
    label = "current plan" if plan.is_current else "previous plan"
    lines = [f'  <plan role="{label}" name="{plan.name}" period="{span}">']
    summary = " · ".join(f"{counts[s]} {s}" for s in ("posted", "scheduled", "drafted", "missed", "upcoming", "discarded", "failed") if counts[s])
    lines.append(f"    {len(plan.days)} days: {summary or 'none'}")
    posted = [d for d in plan.days if d.state == "posted"]
    if posted:
        pillars = Counter(d.pillar for d in posted)
        types = Counter(d.post_type for d in posted)
        lines.append("    pillars posted: " + ", ".join(f"{k} {v}" for k, v in pillars.most_common()))
        lines.append("    types posted: " + ", ".join(f"{k} {v}" for k, v in types.most_common()))
        measured = sorted((d for d in posted if d.signal_value is not None), key=lambda d: -(d.signal_value or 0))
        if measured:
            lines.append("    best posted: " + " | ".join(f"{d.topic[:60]} ({d.post_type}, {d.hook_type or 'no hook tag'}, {d.signal})" for d in measured[:TOP_POSTS]))
            if len(measured) > TOP_POSTS:
                lines.append("    weakest posted: " + " | ".join(f"{d.topic[:60]} ({d.signal})" for d in measured[-TOP_POSTS:][::-1]))
        else:
            lines.append("    no posted day has a metric recorded yet")
    missed = [d for d in plan.days if d.state == "missed"]
    if missed:
        planned_pillars = Counter(d.pillar for d in missed)
        lines.append("    missed (planned, never posted): " + ", ".join(f"{k} {v}" for k, v in planned_pillars.most_common()))
    upcoming = [d for d in plan.days if d.state in ("upcoming", "scheduled", "drafted") and d.on and today <= d.on <= today + timedelta(days=UPCOMING_DAYS)]
    if upcoming:
        lines.append(f"    next {UPCOMING_DAYS} days: " + " | ".join(f"{d.on.isoformat()} {d.topic[:50]} [{d.post_type}, {d.state}]" for d in upcoming))
    strategy = plan.strategy or {}
    bets = [f"{k}: {strategy[k]}" for k in ("exploit", "explore", "lesson", "experiment") if strategy.get(k)]
    if bets:
        lines.append("    what it bet on: " + " · ".join(bets))
    lines.append("  </plan>")
    return lines


def _block(lines: list[str]) -> str:
    return "\n".join(["<plan_review>", *lines, "</plan_review>"])


def review_summary_payload(review: PlanReview | None) -> dict[str, Any]:
    """Numbers for the step chip: what the review found, not its prose."""
    if review is None:
        return {"read": False}
    current = review.current
    return {
        "read": True,
        "plans": len(review.plans),
        "posted": sum(p.counts["posted"] for p in review.plans),
        "missed": sum(p.counts["missed"] for p in review.plans),
        "upcoming": current.counts["upcoming"] + current.counts["scheduled"] if current else 0,
    }


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


__all__ = [
    "DayState",
    "PlanReview",
    "PlanState",
    "load_plan_review",
    "render_plan_review",
    "review_summary_payload",
]
