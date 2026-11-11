"""Scheduled runs (#562): when an occurrence falls, that one process takes it,
that a killed run is retried once, that misses fold into one run, and that
only members reach a schedule."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models.activity import ActivityLog
from models.auth import User
from models.membership import ProjectMember
from models.project import Project
from models.schedule import AgentSchedule
from service import schedules as sched
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

UTC = timezone.utc
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# When an occurrence falls
# ---------------------------------------------------------------------------


def test_a_daily_time_stays_local_across_daylight_saving():
    # Berlin leaves summer time on 25 Oct 2026: 09:00 is 07:00Z before, 08:00Z after.
    before = sched.next_occurrence("daily", "09:00", 0, "Europe/Berlin", datetime(2026, 10, 24, 6, tzinfo=UTC))
    after = sched.next_occurrence("daily", "09:00", 0, "Europe/Berlin", datetime(2026, 10, 26, 6, tzinfo=UTC))
    assert before == datetime(2026, 10, 24, 7, tzinfo=UTC)
    assert after == datetime(2026, 10, 26, 8, tzinfo=UTC)


def test_weekdays_skip_the_weekend_and_weekly_keeps_its_day():
    friday_evening = datetime(2026, 11, 13, 20, tzinfo=UTC)
    assert sched.next_occurrence("weekdays", "09:00", 0, "UTC", friday_evening) == datetime(2026, 11, 16, 9, tzinfo=UTC)
    assert sched.next_occurrence("weekly", "09:00", 0, "UTC", NOW).weekday() == 0
    assert sched.next_occurrence("hourly", "00:15", 0, "UTC", NOW) == datetime(2026, 11, 11, 12, 15, tzinfo=UTC)
    assert sched.next_occurrence("manual", "09:00", 0, "UTC", NOW) is None


def test_jitter_is_stable_per_schedule_and_under_ten_minutes():
    one, two = uuid4(), uuid4()
    assert sched.jitter(one) == sched.jitter(one)
    assert timedelta(0) <= sched.jitter(two) < timedelta(minutes=10)


# ---------------------------------------------------------------------------
# The loop's state
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    # The owner index is partial on Postgres; SQLite would make it unique on
    # project_id alone and refuse a second member.
    with Session(make_sqlite_engine(drop_partial_indexes=True)) as session:
        yield session


def _user(db, email):
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def owner(db):
    return _user(db, "owner@example.com")


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Acme")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


def _schedule(db, project, owner, **kw) -> AgentSchedule:
    row = AgentSchedule(project_id=project.id, user_id=owner.id, job=sched.JobKind.CONTENT_PLAN_FROM_WORK,
                        cadence=kw.pop("cadence", "daily"), at_time="09:00", timezone="UTC", **kw)
    if row.next_run_at is None:
        row.next_run_at = NOW - timedelta(minutes=1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _runs(db, row) -> list[dict]:
    return [r.data for r in db.exec(select(ActivityLog).where(ActivityLog.target_id == str(row.id))
                                    .order_by(ActivityLog.created_at)).all()]


def test_an_occurrence_is_taken_once_and_the_next_is_counted_from_now(db, project, owner):
    row = _schedule(db, project, owner)
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)
    assert claim.occurrence == NOW - timedelta(minutes=1) and claim.attempt == 1
    assert sched.claim_due(db, NOW, sched.Host.CLOUD) == []   # held: nothing to take twice
    db.refresh(row)
    assert row.running_since is not None and row.next_run_at > NOW


def test_a_claim_on_a_stale_read_matches_nothing(db, project, owner):
    """The compare-and-set: of two processes that read the same row, the one
    whose update comes second changes nothing."""
    row = _schedule(db, project, owner)
    seen = row.next_run_at
    sched.claim_due(db, NOW, sched.Host.CLOUD)
    late = db.execute(sa.update(AgentSchedule).where(
        AgentSchedule.id == row.id, AgentSchedule.next_run_at == seen).values(attempt=99))
    assert late.rowcount == 0


def test_a_week_asleep_is_one_run_and_another_host_s_schedule_is_left_alone(db, project, owner):
    row = _schedule(db, project, owner, next_run_at=NOW - timedelta(days=3))
    _schedule(db, project, owner, host=sched.Host.LOCAL)
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)
    assert claim.schedule_id == row.id and claim.late >= timedelta(days=3)
    db.refresh(row)
    assert row.next_run_at > NOW   # the missed days are not queued behind it


def test_a_miss_older_than_a_week_is_skipped_not_run(db, project, owner):
    _schedule(db, project, owner, next_run_at=NOW - timedelta(days=9))
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)
    assert sched.precheck(db, claim, NOW).reason == sched.Reason.STALE


def test_a_killed_run_is_retried_once_then_left(db, project, owner):
    row = _schedule(db, project, owner)
    sched.claim_due(db, NOW, sched.Host.CLOUD)
    later = NOW + sched.LEASE + timedelta(minutes=1)
    assert sched.recover_interrupted(db, later, sched.Host.CLOUD) == 1
    db.refresh(row)
    assert row.running_since is None and row.next_run_at == later and row.attempt == 1
    (retry,) = sched.claim_due(db, later, sched.Host.CLOUD)
    assert retry.attempt == 2 and retry.occurrence == NOW - timedelta(minutes=1)   # the same occurrence
    sched.recover_interrupted(db, later + sched.LEASE * 2, sched.Host.CLOUD)
    db.refresh(row)
    assert row.attempt == 0 and row.next_run_at > later   # back to its own time, not retried again
    outcomes = [r["outcome"] for r in _runs(db, row)]
    assert outcomes == ["interrupted", "interrupted"]


def test_a_transient_failure_retries_once_and_a_missing_key_needs_the_person(db, project, owner):
    row = _schedule(db, project, owner)
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)
    sched.finish(db, claim, sched.JobResult(sched.Outcome.FAILED, "rate_limited", retryable=True), now=NOW, started=NOW)
    db.refresh(row)
    assert row.next_run_at == NOW + sched.RETRY_AFTER and row.attempt == 1
    (retry,) = sched.claim_due(db, NOW + sched.RETRY_AFTER, sched.Host.CLOUD)
    sched.finish(db, retry, sched.JobResult(sched.Outcome.SKIPPED, sched.Reason.NO_KEY), now=NOW, started=NOW)
    db.refresh(row)
    assert row.needs_reason == sched.Reason.NO_KEY and row.attempt == 0 and row.running_since is None


def test_the_cap_counts_runs_that_spent_and_stops_the_next(db, project, owner):
    row = _schedule(db, project, owner, monthly_cap=2)
    for outcome in ("proposed", "nothing_new", "failed"):
        (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD) or [None]
        if claim is None:
            row.next_run_at = NOW - timedelta(minutes=1)
            db.add(row)
            db.commit()
            (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)
        sched.finish(db, claim, sched.JobResult(sched.Outcome(outcome)), now=NOW, started=NOW)
        db.refresh(row)
        row.next_run_at = NOW - timedelta(minutes=1)
        db.add(row)
        db.commit()
    assert sched.spent_this_month(db, row.id, NOW) == 2
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)
    assert sched.precheck(db, claim, NOW).reason == sched.Reason.CAP


def test_a_creator_who_left_the_project_runs_nothing(db, project, owner):
    leaver = _user(db, "left@example.com")
    _schedule(db, project, leaver)
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)
    assert sched.precheck(db, claim, NOW).reason == sched.Reason.NOT_MEMBER


def test_run_claim_records_what_the_job_reported_and_a_crash_as_a_failure(db, project, owner, monkeypatch):
    monkeypatch.setattr(sched, "_db", lambda: _Borrowed(db))
    row = _schedule(db, project, owner)
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)

    async def job(c):
        return sched.JobResult(sched.Outcome.PROPOSED, detail={"feed_days": 2})

    asyncio.run(sched.run_claim(claim, {claim.job: job}, busy=set()))
    db.refresh(row)
    assert row.last_outcome == "proposed" and row.running_since is None
    assert _runs(db, row)[-1]["feed_days"] == 2

    row.next_run_at = NOW - timedelta(minutes=1)
    db.add(row)
    db.commit()
    (claim,) = sched.claim_due(db, NOW, sched.Host.CLOUD)

    async def broken(c):
        raise RuntimeError("boom")

    result = asyncio.run(sched.run_claim(claim, {claim.job: broken}, busy=set()))
    assert result.outcome == sched.Outcome.FAILED and result.retryable
    db.refresh(row)
    assert row.attempt == 1 and row.next_run_at > NOW


class _Borrowed:
    """The test's session, handed to code that opens and closes its own."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------


def test_the_plan_job_reports_nothing_new_and_a_missing_key(monkeypatch):
    import routes.agents as agents_routes
    import routes.content as content_routes
    import routes.schedule_jobs as jobs
    from agents.content.schema import make_session
    from agents.engines import ProviderKeyRequired

    project_id = uuid4()
    monkeypatch.setattr(agents_routes, "_create_session_for",
                        lambda agent, sid, body: make_session(sid, project_id, "plan_month"))

    class Runner:
        async def run_plan(self, session_id, project_id, emit, **kw):
            assert kw["feed"].max_days == 1
            await emit({"event": "pipeline_finished", "outcome": "nothing_new"})

    monkeypatch.setattr(content_routes, "_runner_for", lambda sid, keys: Runner())
    claim = sched.Claim(schedule_id=uuid4(), project_id=project_id, user_id=uuid4(),
                        job=sched.JobKind.CONTENT_PLAN_FROM_WORK, config={"feed": {"max_days": 1}},
                        occurrence=NOW, attempt=1, late=timedelta(0))
    assert asyncio.run(jobs.content_plan_from_work(claim)).outcome == sched.Outcome.NOTHING_NEW

    def no_key(sid, keys):
        raise ProviderKeyRequired("no key")

    monkeypatch.setattr(content_routes, "_runner_for", no_key)
    result = asyncio.run(jobs.content_plan_from_work(claim))
    assert (result.outcome, result.reason) == (sched.Outcome.SKIPPED, sched.Reason.NO_KEY)


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


def _client(db, user):
    import routes.schedules as routes
    import service.auth as auth_service
    from db.session import get_session as get_session_dep

    app = FastAPI()
    app.include_router(routes.router, prefix="/api/user/schedules")
    app.dependency_overrides[get_session_dep] = lambda: db
    if user is not None:
        app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_a_member_creates_runs_pauses_and_reads_a_schedule(db, project, owner, monkeypatch):
    monkeypatch.setattr(sched, "poke", lambda: None)
    api = _client(db, owner)
    made = api.post("/api/user/schedules", json={
        "project_id": str(project.id), "name": "Weekly plan from your work", "cadence": "weekly",
        "weekday": 0, "timezone": "Europe/Berlin", "config": {"feed": {"max_days": 2}, "horizon": 7},
    })
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["host"] == "cloud" and body["next_run_at"] and body["mine"]
    sid = body["id"]
    assert [s["id"] for s in api.get(f"/api/user/schedules?project_id={project.id}").json()] == [sid]
    assert api.post(f"/api/user/schedules/{sid}/run").json()["next_run_at"] is not None
    paused = api.patch(f"/api/user/schedules/{sid}", json={"enabled": False}).json()
    assert paused["enabled"] is False and paused["next_run_at"] is None
    assert api.get(f"/api/user/schedules/{sid}/history").json() == []
    assert api.delete(f"/api/user/schedules/{sid}").status_code == 204


def test_bad_settings_are_refused_where_they_are_written(db, project, owner):
    api = _client(db, owner)
    for body in ({"timezone": "Mars/Base"}, {"at_time": "25:00"},
                 {"config": {"feed": {"max_days": 40}}}, {"config": {"horizon": 30}}):
        res = api.post("/api/user/schedules", json={"project_id": str(project.id), **body})
        assert res.status_code == 422, body
    sid = api.post("/api/user/schedules", json={"project_id": str(project.id)}).json()["id"]
    for change in ({"timezone": "Mars/Base"}, {"at_time": "9am"}, {"config": {"horizon": 3}}):
        assert api.patch(f"/api/user/schedules/{sid}", json=change).status_code == 422, change
    moved = api.patch(f"/api/user/schedules/{sid}", json={"at_time": "7:30", "timezone": "Asia/Tokyo"}).json()
    assert (moved["at_time"], moved["timezone"]) == ("07:30", "Asia/Tokyo")


def test_a_stranger_gets_404_and_a_collaborator_may_pause_but_not_edit(db, project, owner):
    row = _schedule(db, project, owner)
    stranger = _user(db, "stranger@example.com")
    teammate = _user(db, "teammate@example.com")
    db.add(ProjectMember(project_id=project.id, user_id=teammate.id, role="collaborator"))
    db.commit()
    them = _client(db, stranger)
    assert them.get(f"/api/user/schedules?project_id={project.id}").status_code == 404
    assert them.patch(f"/api/user/schedules/{row.id}", json={"enabled": False}).status_code == 404
    assert them.get(f"/api/user/schedules/{row.id}/history").status_code == 404
    assert them.get("/api/user/schedules").json() == []
    mate = _client(db, teammate)
    assert mate.patch(f"/api/user/schedules/{row.id}", json={"enabled": False}).status_code == 200
    assert mate.patch(f"/api/user/schedules/{row.id}", json={"cadence": "daily"}).status_code == 403
    assert mate.delete(f"/api/user/schedules/{row.id}").status_code == 403
