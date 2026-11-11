"""Scheduled runs (issue #562): one loop over one table, the same code in the
cloud and on a laptop.

Runs here are few and long, a handful a week per project and each a
multi-minute agent session, so this is a clock, not a task queue. The
reasoning, and the queues it was weighed against, are in
``docs/engineering/2026-11-11-scheduled-runs-research.md``.

The rules, each a way the obvious version goes wrong:

* **A schedule runs only in the backend that owns its row** (``host``). The
  loop claims rows for its own host, so a desktop schedule never reaches the
  cloud and the cloud never runs one with a laptop's credentials.
* **One process takes an occurrence.** ``claim_due`` is a compare-and-set on
  ``next_run_at``, which holds on SQLite and Postgres alike, so the two copies
  Railway runs for a moment during a deploy cannot both fire it.
* **A run holds a lease and renews it.** A lease that lapses means a deploy
  or a quit app killed the run, and the next tick records it as interrupted
  and retries it once. A retry is safe because a run's output is a proposal,
  never a publish.
* **Missed runs coalesce.** The next occurrence is computed from now, not from
  the one missed, so a laptop asleep for a week runs once when it wakes and
  then keeps its weekly time; a miss older than ``CATCH_UP_DAYS`` is recorded
  and skipped. The tick needs no wake detection for this: anything due is
  claimed on the first tick after the process can run at all.
* **Retries are classified, not counted blind.** A transient failure (a
  model's 429 or 5xx, the network, an interruption) is retried once after
  ``RETRY_AFTER``; a deterministic one (no saved key, the cap reached, the
  creator no longer a member) never is, and says what the person must do.
* **What happened is an ``activity_logs`` row** (category ``schedule``),
  linked to the conversation the run produced, never a second history table.

No agent framework and no route imports here: the jobs are handed in by the
caller (``server.py``'s lifespan), so this module stays the clock alone.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from sqlmodel import select

from models.activity import ActivityLog
from models.schedule import AgentSchedule
from utils.dates import utcnow

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
LEASE = timedelta(minutes=3)
RENEW_EVERY = 60
RUN_TIMEOUT = timedelta(minutes=15)
CATCH_UP_DAYS = 7
RETRY_AFTER = timedelta(minutes=15)
MAX_ATTEMPTS = 2
JITTER_SECONDS = 10 * 60
MAX_RUNNING = 2
CLAIM_BATCH = 10
HISTORY_LIMIT = 50
ACTIVITY_CATEGORY = "schedule"


class Cadence(StrEnum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"
    MANUAL = "manual"


class Host(StrEnum):
    CLOUD = "cloud"
    LOCAL = "local"


class JobKind(StrEnum):
    """What a schedule runs. Values are stored, so never rename one; only add."""

    CONTENT_PLAN_FROM_WORK = "content.plan_from_work"


class Outcome(StrEnum):
    """What one run came to: the History column and ``last_outcome``."""

    PROPOSED = "proposed"          # a plan proposal is waiting on the person
    NOTHING_NEW = "nothing_new"    # the gate found nothing worth a model call
    NO_PROPOSAL = "no_proposal"    # the model ran and proposed nothing
    FAILED = "failed"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"


class Reason(StrEnum):
    """Why a run was skipped or failed, as a code the app words."""

    STALE = "stale"                    # missed by more than CATCH_UP_DAYS
    CAP = "monthly_cap"
    NOT_MEMBER = "not_member"
    NO_KEY = "no_model_key"
    PROJECT_BUSY = "project_busy"      # a run for the same project is still going
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"        # killed by a deploy or a quit app
    ERROR = "error"
    UNKNOWN_JOB = "unknown_job"


# Outcomes that spent a model call, which is what the monthly cap counts.
SPENT = frozenset({Outcome.PROPOSED, Outcome.NO_PROPOSAL, Outcome.FAILED})
# Reasons only the person can clear: the schedule says "Needs you" until then.
NEEDS_YOU = frozenset({Reason.NOT_MEMBER, Reason.NO_KEY, Reason.CAP})


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


def zone_of(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def parse_hhmm(value: str) -> time:
    try:
        hh, mm = (int(p) for p in str(value or "09:00").split(":", 1))
        return time(min(max(hh, 0), 23), min(max(mm, 0), 59))
    except ValueError:
        return time(9, 0)


def next_occurrence(cadence: str, at_time: str, weekday: int, tz: str, after: datetime) -> datetime | None:
    """The first wall-clock occurrence strictly after ``after``, in UTC, or None
    for a manual schedule. Daily, weekday and weekly times are local times, so
    09:00 stays 09:00 across a daylight-saving change."""
    if cadence == Cadence.MANUAL or cadence not in set(Cadence):
        return None
    after = after.astimezone(timezone.utc)
    at = parse_hhmm(at_time)
    if cadence == Cadence.HOURLY:
        candidate = after.replace(minute=at.minute, second=0, microsecond=0)
        return candidate if candidate > after else candidate + timedelta(hours=1)
    zone = zone_of(tz)
    local = after.astimezone(zone)
    for offset in range(0, 9):
        day: date = local.date() + timedelta(days=offset)
        if cadence == Cadence.WEEKDAYS and day.weekday() >= 5:
            continue
        if cadence == Cadence.WEEKLY and day.weekday() != (weekday % 7):
            continue
        candidate = datetime.combine(day, at, zone).astimezone(timezone.utc)
        if candidate > after:
            return candidate
    return None


def jitter(schedule_id: UUID) -> timedelta:
    """A fixed offset per schedule, so a thousand 09:00 runs do not reach the
    model providers in the same second. Derived from the id: stable, and
    nothing to store."""
    digest = hashlib.sha256(str(schedule_id).encode()).hexdigest()
    return timedelta(seconds=int(digest[:8], 16) % JITTER_SECONDS)


def next_run_after(row: AgentSchedule, after: datetime) -> datetime | None:
    occurrence = next_occurrence(row.cadence, row.at_time, row.weekday, row.timezone, after)
    return occurrence + jitter(row.id) if occurrence else None


# ---------------------------------------------------------------------------
# Claims and outcomes (sync; the loop calls these off the event loop)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """One occurrence this process took: what the job reads."""

    schedule_id: UUID
    project_id: UUID
    user_id: UUID
    job: str
    config: dict
    occurrence: datetime
    attempt: int
    late: timedelta


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def recover_interrupted(db: Any, now: datetime, host: str) -> int:
    """Runs whose lease lapsed were killed mid-run. Each is recorded as
    interrupted and, on its first attempt, put back for one retry now."""
    rows = db.exec(
        select(AgentSchedule).where(
            AgentSchedule.host == host,
            AgentSchedule.running_since.is_not(None),
            AgentSchedule.lease_until < now,
        )
    ).all()
    for row in rows:
        retry = row.attempt < MAX_ATTEMPTS and row.enabled
        _record(db, row, Outcome.INTERRUPTED, now=now, reason=Reason.INTERRUPTED,
                data={"occurrence": _iso(row.occurrence), "attempt": row.attempt, "will_retry": retry})
        row.running_since = row.lease_until = None
        row.last_outcome, row.last_run_at = Outcome.INTERRUPTED, now
        if retry:
            row.next_run_at = now
        else:
            row.attempt, row.occurrence = 0, None
        row.updated_at = now
        db.add(row)
    db.commit()
    return len(rows)


def claim_due(db: Any, now: datetime, host: str) -> list[Claim]:
    """Take every occurrence due on this host that no other process holds.

    The update matches on the ``next_run_at`` this read saw, so of two
    processes reading the same row one changes it and the other's update
    touches nothing. The next occurrence is counted from now, which is what
    folds a week of missed runs into one."""
    rows = db.exec(
        select(AgentSchedule).where(
            AgentSchedule.enabled.is_(True),
            AgentSchedule.host == host,
            AgentSchedule.next_run_at.is_not(None),
            AgentSchedule.next_run_at <= now,
            AgentSchedule.running_since.is_(None),
        ).order_by(AgentSchedule.next_run_at).limit(CLAIM_BATCH)
    ).all()
    claims: list[Claim] = []
    for row in rows:
        seen = row.next_run_at
        retrying = row.attempt > 0 and row.occurrence is not None
        occurrence = _aware(row.occurrence) if retrying else _aware(seen)
        attempt = row.attempt + 1 if retrying else 1
        result = db.execute(
            sa.update(AgentSchedule)
            .where(AgentSchedule.id == row.id, AgentSchedule.next_run_at == seen,
                   AgentSchedule.running_since.is_(None))
            .values(next_run_at=next_run_after(row, now), lease_until=now + LEASE, running_since=now,
                    occurrence=occurrence, attempt=attempt, updated_at=now)
        )
        if result.rowcount == 1:
            claims.append(Claim(
                schedule_id=row.id, project_id=row.project_id, user_id=row.user_id, job=row.job,
                config=dict(row.config or {}), occurrence=occurrence, attempt=attempt,
                late=max(now - occurrence, timedelta(0)),
            ))
    db.commit()
    return claims


def renew_lease(db: Any, schedule_id: UUID, now: datetime) -> None:
    db.execute(
        sa.update(AgentSchedule)
        .where(AgentSchedule.id == schedule_id, AgentSchedule.running_since.is_not(None))
        .values(lease_until=now + LEASE)
    )
    db.commit()


@dataclass
class JobResult:
    """What a job reports back to the loop."""

    outcome: Outcome
    reason: str = ""
    conversation_id: UUID | None = None
    cost_usd: float | None = None
    retryable: bool = False
    detail: dict = field(default_factory=dict)


def finish(db: Any, claim: Claim, result: JobResult, *, now: datetime, started: datetime) -> AgentSchedule | None:
    """Release the claim, record the run, and set what the page shows.

    A transient failure on the first attempt is put back for one retry after
    ``RETRY_AFTER``; the schedule's own next occurrence then follows it."""
    row = db.get(AgentSchedule, claim.schedule_id)
    if row is None:
        return None
    retry = (result.outcome in (Outcome.FAILED, Outcome.INTERRUPTED) and result.retryable
             and claim.attempt < MAX_ATTEMPTS and row.enabled)
    _record(db, row, result.outcome, now=now, reason=result.reason, conversation_id=result.conversation_id, data={
        "occurrence": _iso(claim.occurrence),
        "attempt": claim.attempt,
        "late_seconds": int(claim.late.total_seconds()),
        "duration_seconds": int((now - started).total_seconds()),
        "cost_usd": result.cost_usd,
        "will_retry": retry,
        **result.detail,
    })
    row.running_since = row.lease_until = None
    row.last_run_at, row.last_outcome = now, result.outcome
    row.needs_reason = result.reason if result.reason in NEEDS_YOU else ""
    if retry:
        row.next_run_at = now + RETRY_AFTER
    else:
        row.attempt, row.occurrence = 0, None
    row.updated_at = now
    db.add(row)
    db.commit()
    return row


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def _record(db: Any, row: AgentSchedule, outcome: str, *, now: datetime, reason: str = "",
            conversation_id: UUID | None = None, data: dict | None = None) -> None:
    from service.activity import log_activity

    log_activity(
        db, category=ACTIVITY_CATEGORY, action="run", source="auto",
        project_id=row.project_id, user_id=row.user_id, conversation_id=conversation_id,
        target_type="schedule", target_id=str(row.id),
        data={"outcome": str(outcome), "reason": str(reason), "job": row.job, **(data or {})},
    )


def spent_this_month(db: Any, schedule_id: UUID, now: datetime) -> int:
    """Runs this calendar month (UTC) that called a model: the cap's count."""
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.exec(
        select(ActivityLog).where(
            ActivityLog.category == ACTIVITY_CATEGORY,
            ActivityLog.target_id == str(schedule_id),
            ActivityLog.created_at >= start,
        )
    ).all()
    return sum(1 for r in rows if (r.data or {}).get("outcome") in SPENT)


def history(db: Any, schedule_id: UUID, limit: int = HISTORY_LIMIT) -> list[dict]:
    rows = db.exec(
        select(ActivityLog)
        .where(ActivityLog.category == ACTIVITY_CATEGORY, ActivityLog.target_id == str(schedule_id))
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    ).all()
    return [{
        "at": _iso(r.created_at),
        "outcome": (r.data or {}).get("outcome", ""),
        "reason": (r.data or {}).get("reason", ""),
        "conversation_id": str(r.conversation_id) if r.conversation_id else None,
        "cost_usd": (r.data or {}).get("cost_usd"),
        "duration_seconds": (r.data or {}).get("duration_seconds"),
        "late_seconds": (r.data or {}).get("late_seconds"),
        "will_retry": bool((r.data or {}).get("will_retry")),
        "feed_days": (r.data or {}).get("feed_days"),
    } for r in rows]


def precheck(db: Any, claim: Claim, now: datetime) -> JobResult | None:
    """What stops a run before it spends anything: a miss too old to be worth
    it, a creator who is no longer a member, a month's cap already spent."""
    from service.membership import member_role

    if claim.late > timedelta(days=CATCH_UP_DAYS):
        return JobResult(Outcome.SKIPPED, Reason.STALE)
    if member_role(claim.project_id, claim.user_id, db) is None:
        return JobResult(Outcome.SKIPPED, Reason.NOT_MEMBER)
    row = db.get(AgentSchedule, claim.schedule_id)
    if row is not None and spent_this_month(db, claim.schedule_id, now) >= row.monthly_cap:
        return JobResult(Outcome.SKIPPED, Reason.CAP)
    return None


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

JobFn = Callable[[Claim], Awaitable[JobResult]]

# Set by "Run now" so the loop does not wait out its tick.
_poke = asyncio.Event()


def poke() -> None:
    try:
        _poke.set()
    except RuntimeError:  # no running loop (a sync test); the next tick finds it
        pass


def _db() -> Any:
    from db.session import get_session as db_session

    return next(db_session())


def _tick_sync(now: datetime, host: str) -> list[Claim]:
    with _db() as db:
        recover_interrupted(db, now, host)
        return claim_due(db, now, host)


async def run_claim(claim: Claim, jobs: dict[str, JobFn], *, busy: set[UUID]) -> JobResult:
    """One claimed occurrence, end to end: precheck, the job under its lease
    and timeout, the outcome recorded. Never raises."""
    started = utcnow()
    result: JobResult | None = None
    try:
        with _db() as db:
            result = precheck(db, claim, started)
        if result is None and claim.project_id in busy:
            result = JobResult(Outcome.SKIPPED, Reason.PROJECT_BUSY)
        if result is None:
            job = jobs.get(claim.job)
            if job is None:
                result = JobResult(Outcome.SKIPPED, Reason.UNKNOWN_JOB)
            else:
                busy.add(claim.project_id)
                renewer = asyncio.create_task(_renew(claim.schedule_id))
                try:
                    result = await asyncio.wait_for(job(claim), RUN_TIMEOUT.total_seconds())
                except asyncio.TimeoutError:
                    result = JobResult(Outcome.FAILED, Reason.TIMEOUT)
                finally:
                    renewer.cancel()
                    busy.discard(claim.project_id)
    except Exception:  # noqa: BLE001 — recorded as a failure, never fatal to the loop
        logger.exception("schedules: run of %s failed", claim.schedule_id)
        result = JobResult(Outcome.FAILED, Reason.ERROR, retryable=True)
    with _db() as db:
        finish(db, claim, result, now=utcnow(), started=started)
    return result


async def _renew(schedule_id: UUID) -> None:
    while True:
        await asyncio.sleep(RENEW_EVERY)
        await asyncio.to_thread(lambda: _renew_sync(schedule_id))


def _renew_sync(schedule_id: UUID) -> None:
    with _db() as db:
        renew_lease(db, schedule_id, utcnow())


async def run_scheduler(jobs: dict[str, JobFn], *, host: str, tick: float = TICK_SECONDS) -> None:
    """Tick forever: claim what is due on this host, run it, record it. Two
    runs at once at most, one per project."""
    running: set[asyncio.Task] = set()
    busy: set[UUID] = set()
    gate = asyncio.Semaphore(MAX_RUNNING)

    async def _bounded(claim: Claim) -> None:
        async with gate:
            await run_claim(claim, jobs, busy=busy)

    while True:
        try:
            for claim in await asyncio.to_thread(_tick_sync, utcnow(), host):
                task = asyncio.create_task(_bounded(claim), name=f"schedule-{claim.schedule_id}")
                running.add(task)
                task.add_done_callback(running.discard)
        except Exception:  # noqa: BLE001 — a bad tick must not end the loop
            logger.exception("schedules: tick failed")
        _poke.clear()
        try:
            await asyncio.wait_for(_poke.wait(), tick)
        except asyncio.TimeoutError:
            pass


def host_for(duct_local: bool) -> str:
    return Host.LOCAL if duct_local else Host.CLOUD


__all__ = [
    "Cadence",
    "Claim",
    "Host",
    "JobKind",
    "JobResult",
    "Outcome",
    "Reason",
    "claim_due",
    "finish",
    "history",
    "host_for",
    "jitter",
    "next_occurrence",
    "next_run_after",
    "poke",
    "precheck",
    "recover_interrupted",
    "run_claim",
    "run_scheduler",
    "spent_this_month",
]
