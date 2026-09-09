"""Persist and read what model calls cost.

Two halves, and the split matters:

* ``UsagePersister`` wraps a runner's ``emit`` and stores every ``TOKEN_USAGE``
  event. That is the same seam ``ArtifactPersister`` uses, and for the same
  reason: the runner already emits the fact, the route already knows whose run
  it is, and a persister in between needs no cooperation from either. One
  wrapper per agent route and every agent is covered — which is what "works
  across the whole product" has to mean if it is not going to rot.
* ``summarise`` answers the page. Aggregation happens in SQL, not in Python
  over every row: a busy month is tens of thousands of calls and the answer is
  a dozen numbers.

Storage never blocks the stream. The SSE write happens first and a failure to
record usage is logged, never raised — losing a row from an accounting view is
bad, and dropping a user's agent run because the accounting write failed is
worse.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

import sqlalchemy as sa

from agents.core.events import AgentEvent
from db.session import get_session as db_session
from utils.dates import utcnow
from models.usage import ModelUsage

logger = logging.getLogger(__name__)

# A dollar is a million micros. Named because `1_000_000` appearing beside a
# token count reads like a token count.
MICROS_PER_USD = 1_000_000

# What the page defaults to. Long enough that a weekly brief appears in it,
# short enough that "this is what Duct is costing me" stays a current answer.
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 365


def _micros(cost_usd: object) -> int | None:
    """Dollars to integer micros, or None when the price is unknown.

    Unknown is not zero. A model missing from the price table would otherwise
    contribute a confident $0.00 to a total whose only job is to be trusted.
    """
    if not isinstance(cost_usd, (int, float)) or isinstance(cost_usd, bool):
        return None
    return round(float(cost_usd) * MICROS_PER_USD)


def record_usage_event(
    body: dict,
    *,
    user_id: UUID | None,
    project_id: UUID | None,
    conversation_id: UUID | None,
    agent_type: str,
    provider: str = "",
    tier: str = "",
) -> None:
    """Store one TOKEN_USAGE event. Synchronous; call it off the loop."""
    row = ModelUsage(
        user_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
        agent_type=agent_type,
        provider=provider,
        # The provider's own answer for which model replied, which is not always
        # the one asked for: a fallback step or an alias resolves here. Recording
        # what answered is what makes a step-down visible in the numbers later.
        model=str(body.get("model") or ""),
        tier=tier,
        scope=str(body.get("scope") or "thread"),
        input_tokens=int(body.get("input_tokens") or 0),
        output_tokens=int(body.get("output_tokens") or 0),
        cache_read_tokens=int(body.get("cache_read_tokens") or 0),
        cache_creation_tokens=int(body.get("cache_creation_tokens") or 0),
        cost_micros=_micros(body.get("cost_usd")),
    )
    with next(db_session()) as db:
        db.add(row)
        db.commit()


class UsagePersister:
    """Wraps ``emit`` and records every ``TOKEN_USAGE`` that goes past."""

    def __init__(
        self,
        *,
        user_id: UUID | None,
        project_id: UUID | None,
        conversation_id: UUID | None = None,
        agent_type: str = "",
        provider: str = "",
        tier: str = "",
    ) -> None:
        self.user_id = user_id
        self.project_id = project_id
        self.conversation_id = conversation_id
        self.agent_type = agent_type
        # Provider and tier are properties of the run, not of the call, so they
        # come from the route's resolution rather than from the event.
        self.provider = provider
        self.tier = tier

    def wrap_emit(self, emit_fn):
        async def _emit(body: dict) -> None:
            await emit_fn(body)  # SSE first — streaming never waits on storage
            if body.get("event") != AgentEvent.TOKEN_USAGE or body.get("replay"):
                return
            try:
                await asyncio.to_thread(
                    record_usage_event,
                    body,
                    user_id=self.user_id,
                    project_id=self.project_id,
                    conversation_id=self.conversation_id,
                    agent_type=self.agent_type,
                    provider=self.provider,
                    tier=self.tier,
                )
            except Exception:  # noqa: BLE001 — accounting never fails a run
                logger.warning("usage: failed to record a model call", exc_info=True)

        return _emit


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@dataclass
class UsageSlice:
    """One row of a breakdown: a name plus what it cost."""

    key: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_micros: int | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "total_tokens": self.total_tokens,
            # Dollars at the edge, micros everywhere inside.
            "cost_usd": None if self.cost_micros is None else self.cost_micros / MICROS_PER_USD,
        }


@dataclass
class UsageSummary:
    window_days: int
    since: datetime
    total: UsageSlice = field(default_factory=lambda: UsageSlice(key="total"))
    by_agent: list[UsageSlice] = field(default_factory=list)
    by_model: list[UsageSlice] = field(default_factory=list)
    by_provider: list[UsageSlice] = field(default_factory=list)
    daily: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "window_days": self.window_days,
            "since": self.since.isoformat(),
            "total": self.total.as_dict(),
            "by_agent": [s.as_dict() for s in self.by_agent],
            "by_model": [s.as_dict() for s in self.by_model],
            "by_provider": [s.as_dict() for s in self.by_provider],
            "daily": self.daily,
        }


def _slice_from_row(key: str, row) -> UsageSlice:
    return UsageSlice(
        key=key or "unknown",
        calls=int(row.calls or 0),
        input_tokens=int(row.input_tokens or 0),
        output_tokens=int(row.output_tokens or 0),
        cached_tokens=int(row.cached_tokens or 0),
        # SUM over a nullable column is NULL only when every row was NULL, which
        # is exactly the "we do not know what this cost" case worth preserving.
        cost_micros=None if row.cost_micros is None else int(row.cost_micros),
    )


_AGGREGATES = (
    sa.func.count().label("calls"),
    sa.func.coalesce(sa.func.sum(ModelUsage.input_tokens), 0).label("input_tokens"),
    sa.func.coalesce(sa.func.sum(ModelUsage.output_tokens), 0).label("output_tokens"),
    sa.func.coalesce(sa.func.sum(ModelUsage.cache_read_tokens), 0).label("cached_tokens"),
    sa.func.sum(ModelUsage.cost_micros).label("cost_micros"),
)


def summarise(
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> UsageSummary:
    """Totals and breakdowns for one user, optionally narrowed to a project.

    Scoped to ``user_id`` unconditionally. This is spending data, and the row
    that pays for a run is the caller's — so the query is the boundary rather
    than a check beside it.
    """
    days = max(1, min(int(window_days or DEFAULT_WINDOW_DAYS), MAX_WINDOW_DAYS))
    since = utcnow() - timedelta(days=days)
    summary = UsageSummary(window_days=days, since=since)

    with next(db_session()) as db:
        where = [ModelUsage.user_id == user_id, ModelUsage.created_at >= since]
        if project_id is not None:
            where.append(ModelUsage.project_id == project_id)

        total = db.execute(sa.select(*_AGGREGATES).where(*where)).one()
        summary.total = _slice_from_row("total", total)

        for column, target in (
            (ModelUsage.agent_type, summary.by_agent),
            (ModelUsage.model, summary.by_model),
            (ModelUsage.provider, summary.by_provider),
        ):
            rows = db.execute(
                sa.select(column, *_AGGREGATES)
                .where(*where)
                .group_by(column)
                # Cost first so the expensive thing is the first thing read; a
                # NULL cost sorts last rather than looking free.
                .order_by(sa.func.coalesce(sa.func.sum(ModelUsage.cost_micros), 0).desc())
            ).all()
            target.extend(_slice_from_row(row[0], row) for row in rows)

        # Date bucketing in SQL differs per dialect (date_trunc vs date()), and
        # this table is the one place the desktop build and the deployment must
        # agree. A day is a string either way, so cast and group on that.
        day = sa.func.substr(sa.cast(ModelUsage.created_at, sa.String()), 1, 10).label("day")
        rows = db.execute(
            sa.select(day, *_AGGREGATES).where(*where).group_by(day).order_by(day)
        ).all()
        summary.daily = [
            {
                "day": row.day,
                "calls": int(row.calls or 0),
                "total_tokens": int(row.input_tokens or 0) + int(row.output_tokens or 0),
                "cost_usd": None if row.cost_micros is None else int(row.cost_micros) / MICROS_PER_USD,
            }
            for row in rows
        ]

    return summary
