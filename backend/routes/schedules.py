"""Schedules (issue #562): list, create, edit, pause, run now, delete, history.

Every route is a project member's: a schedule is a project-scoped row, read
and written through ``get_project_for_user`` / ``get_project_row_for_user``,
and a non-member gets 404, never 403. Any member may pause, resume or run
one; changing what it does or deleting it is for its creator or the project's
owner, because a run acts as its creator and spends that person's key.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session, select
from starlette.status import HTTP_403_FORBIDDEN, HTTP_409_CONFLICT

from config import get_configs
from db.session import get_session as db_session
from models.auth import User
from models.schedule import AgentSchedule
from service.auth import get_current_user
from models.membership import ROLE_OWNER
from service.membership import accessible_projects, get_project_for_user, get_project_row_for_user, member_role
from service import schedules as sched
from utils.dates import utcnow

router = APIRouter(tags=["schedules"], dependencies=[Depends(get_current_user)])

Cadence = Literal["hourly", "daily", "weekdays", "weekly", "manual"]
HORIZONS = (7, 14)
MAX_MONTHLY_CAP = 31


def _check_config(job: str, config: dict) -> dict:
    """A job's own settings, validated where they are written, so a run never
    fails on a typo saved a week earlier."""
    if job == sched.JobKind.CONTENT_PLAN_FROM_WORK:
        from agents.content.feed import FeedOptions

        try:
            feed = FeedOptions.model_validate(config.get("feed") or {})
        except Exception as exc:  # noqa: BLE001 — a 422 with the reason
            raise HTTPException(422, f"Invalid feed options: {exc}") from exc
        horizon = int(config.get("horizon") or 7)
        if horizon not in HORIZONS:
            raise HTTPException(422, f"horizon must be one of {HORIZONS}")
        return {"feed": feed.model_dump(mode="json"), "horizon": horizon}
    raise HTTPException(422, f"Unknown job {job!r}")


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    job: str = sched.JobKind.CONTENT_PLAN_FROM_WORK
    name: str = Field(default="", max_length=120)
    cadence: Cadence = "weekly"
    at_time: str = "09:00"
    weekday: int = Field(default=0, ge=0, le=6)
    timezone: str = "UTC"
    monthly_cap: int = Field(default=6, ge=1, le=MAX_MONTHLY_CAP)
    config: dict = Field(default_factory=dict)

    @field_validator("at_time")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        hh, _, mm = value.partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError("at_time is HH:MM")
        return f"{int(hh):02d}:{int(mm):02d}"

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str) -> str:
        if sched.zone_of(value).key != (value or "UTC"):
            raise ValueError(f"unknown time zone {value!r}")
        return value


class SchedulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    cadence: Cadence | None = None
    at_time: str | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    timezone: str | None = None
    monthly_cap: int | None = Field(default=None, ge=1, le=MAX_MONTHLY_CAP)
    config: dict | None = None
    enabled: bool | None = None

    _hhmm = field_validator("at_time")(lambda cls, v: v if v is None else ScheduleIn._hhmm(v))  # type: ignore[arg-type]
    _zone = field_validator("timezone")(lambda cls, v: v if v is None else ScheduleIn._zone(v))  # type: ignore[arg-type]


RECENT_RUNS = 8


def _iso(value: datetime | None) -> str | None:
    return sched._aware(value).isoformat() if value else None


def _out(db: Session, row: AgentSchedule, user: User) -> dict[str, Any]:
    now = utcnow()
    # The last few runs ride on the list, so the card can draw its run strip
    # without a history request per schedule; the full history stays a fold.
    recent = sched.history(db, row.id, limit=RECENT_RUNS)
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "job": row.job,
        "name": row.name,
        "cadence": row.cadence,
        "at_time": row.at_time,
        "weekday": row.weekday,
        "timezone": row.timezone,
        "enabled": row.enabled,
        "host": row.host,
        "monthly_cap": row.monthly_cap,
        "config": row.config or {},
        "next_run_at": _iso(row.next_run_at) if row.enabled else None,
        "last_run_at": _iso(row.last_run_at),
        "last_outcome": row.last_outcome,
        "needs_reason": row.needs_reason,
        "running": row.running_since is not None,
        "runs_this_month": sched.spent_this_month(db, row.id, now),
        "last": recent[0] if recent else None,
        "recent": [{"at": r["at"], "outcome": r["outcome"], "will_retry": r["will_retry"]} for r in recent],
        "mine": row.user_id == user.id,
    }


def _may_change(db: Session, row: AgentSchedule, user: User) -> None:
    if row.user_id != user.id and member_role(row.project_id, user.id, db) != ROLE_OWNER:
        raise HTTPException(HTTP_403_FORBIDDEN, "Only the schedule's creator or the project owner can change it.")


def _here() -> str:
    return sched.host_for(get_configs().duct_local)


@router.get("")
def list_schedules(project_id: UUID | None = None, user: User = Depends(get_current_user),
                   db: Session = Depends(db_session)) -> list[dict]:
    """This backend's schedules for one project, or for every project the
    caller belongs to. A schedule another host owns is never listed here: it
    is not this backend's to run or to change."""
    if project_id is not None:
        get_project_for_user(project_id, user, db)
        ids = [project_id]
    else:
        ids = [p.id for p in accessible_projects(user, db)]
    if not ids:
        return []
    rows = db.exec(
        select(AgentSchedule)
        .where(AgentSchedule.project_id.in_(ids), AgentSchedule.host == _here())
        .order_by(AgentSchedule.created_at)
    ).all()
    return [_out(db, r, user) for r in rows]


@router.post("", status_code=201)
def create_schedule(body: ScheduleIn, user: User = Depends(get_current_user),
                    db: Session = Depends(db_session)) -> dict:
    get_project_for_user(body.project_id, user, db)
    now = utcnow()
    row = AgentSchedule(
        project_id=body.project_id, user_id=user.id, job=body.job, name=body.name.strip(),
        config=_check_config(body.job, body.config), cadence=body.cadence, at_time=body.at_time,
        weekday=body.weekday, timezone=body.timezone, monthly_cap=body.monthly_cap, host=_here(),
        created_at=now, updated_at=now,
    )
    row.next_run_at = sched.next_run_after(row, now)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(db, row, user)


@router.patch("/{schedule_id}")
def update_schedule(schedule_id: UUID, body: SchedulePatch, user: User = Depends(get_current_user),
                    db: Session = Depends(db_session)) -> dict:
    row = get_project_row_for_user(db, user, AgentSchedule, schedule_id, label="Schedule")
    changes = body.model_dump(exclude_unset=True)
    if set(changes) - {"enabled"}:
        _may_change(db, row, user)
    if "config" in changes:
        changes["config"] = _check_config(row.job, changes["config"] or {})
    for key, value in changes.items():
        setattr(row, key, value)
    now = utcnow()
    if row.enabled:
        # A resumed schedule picks up from now, not from the week it missed
        # while paused; a person's fix to a "Needs you" clears the note.
        if row.running_since is None:
            row.next_run_at = sched.next_run_after(row, now)
        if "enabled" in changes or "config" in changes:
            row.needs_reason = ""
    else:
        row.next_run_at = None
    row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(db, row, user)


@router.post("/{schedule_id}/run")
def run_now(schedule_id: UUID, user: User = Depends(get_current_user),
            db: Session = Depends(db_session)) -> dict:
    """Run the schedule's job at once. Its weekly time stays where it was: the
    next occurrence after this run is computed from the schedule, not from it."""
    row = get_project_row_for_user(db, user, AgentSchedule, schedule_id, label="Schedule")
    if row.running_since is not None:
        raise HTTPException(HTTP_409_CONFLICT, "This schedule is already running.")
    row.next_run_at = utcnow()
    row.enabled = True
    row.needs_reason = ""
    db.add(row)
    db.commit()
    db.refresh(row)
    sched.poke()
    return _out(db, row, user)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: UUID, user: User = Depends(get_current_user),
                    db: Session = Depends(db_session)) -> None:
    """Delete the schedule. Its history stays in the project's activity: the
    runs happened, and the conversations they left are still the person's."""
    row = get_project_row_for_user(db, user, AgentSchedule, schedule_id, label="Schedule")
    _may_change(db, row, user)
    db.delete(row)
    db.commit()


@router.get("/{schedule_id}/history")
def schedule_history(schedule_id: UUID, user: User = Depends(get_current_user),
                     db: Session = Depends(db_session)) -> list[dict]:
    row = get_project_row_for_user(db, user, AgentSchedule, schedule_id, label="Schedule")
    return sched.history(db, row.id)
