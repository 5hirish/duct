"""A plan from shipped work (#561), end to end in the harness: the read step,
the no-model-call exit, and the plan tools holding every cited source to
what the run was shown."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from agents.content.feed import FeedDigest, FeedItem, FeedOptions
from agents.core.events import AgentEvent, AgentStep, EventKind

TODAY = date(2031, 10, 7)


@pytest.fixture
def engine(monkeypatch):
    from tests.conftest import make_sqlite_engine

    import agents.content.tools as content_tools
    import db.session as db_session

    eng = make_sqlite_engine()
    monkeypatch.setattr(db_session, "get_engine", lambda: eng)
    monkeypatch.setattr(content_tools, "get_engine", lambda: eng)
    return eng


def _digest(*items: FeedItem, max_days: int = 2) -> FeedDigest:
    return FeedDigest(window_from=date(2031, 9, 24), window_to=TODAY,
                      options=FeedOptions(max_days=max_days), items=list(items))


PR = FeedItem(ref="gh:pr-412", kind="pull_request", title="Retry the GA4 handshake",
              url="https://github.com/o/r/pull/412")
RELEASE = FeedItem(ref="gh:r-v1.4.0", kind="release", title="v1.4.0", url="https://github.com/o/r/releases/v1.4.0")


def _tool(session, name: str):
    from agents.content.tools import build_content_tools_lc

    async def emit(_body: dict) -> None:
        return None

    return {t.name: t for t in build_content_tools_lc(session.project_id, emit, session)}[name]


def _submit(session, days: list[dict]) -> dict:
    plan = {"type": "plan", "project_id": str(session.project_id), "days": days}
    return json.loads(asyncio.run(_tool(session, "submit_plan").ainvoke({"plan": plan})))


def _session(feed: FeedDigest | None = None):
    from agents.content.schema import make_session

    session = make_session("s", uuid4(), "plan_month")
    session.period_start, session.period_days = TODAY, 3
    session.feed = feed
    return session


def test_a_feed_day_is_proposed_with_the_feed_s_title_and_link_and_the_window_rides_along(engine):
    session = _session(_digest(PR, RELEASE))
    out = _submit(session, [
        {"topic": "Onboarding keeps GA4", "pillar": "Product", "sources": [{"ref": "gh:pr-412", "title": "x"}]},
        {"topic": "t1", "pillar": "p"},
        {"topic": "t2", "pillar": "p"},
    ])
    assert out["status"] == "proposed", out
    first = session.proposal.days[0]
    assert first["sources"] == [{"ref": "gh:pr-412", "kind": "pull_request",
                                 "title": "Retry the GA4 handshake", "url": "https://github.com/o/r/pull/412"}]
    assert session.proposal.days[1]["sources"] == []
    assert session.proposal.strategy["feed"]["window_to"] == TODAY.isoformat()


def test_a_ref_the_run_was_not_shown_or_too_many_feed_days_are_refused(engine):
    session = _session(_digest(PR, RELEASE, max_days=1))
    out = _submit(session, [
        {"topic": "a", "pillar": "p", "sources": [{"ref": "gh:pr-999"}]},
        {"topic": "b", "pillar": "p", "sources": [{"ref": "gh:r-v1.4.0"}]},
        {"topic": "c", "pillar": "p"},
    ])
    assert "error" in json.dumps(out).lower()
    assert "gh:pr-999 is not in this run's feed" in json.dumps(out)
    assert "at most 1" in json.dumps(out)
    assert session.proposal is None


def test_a_plan_from_goals_cannot_cite_a_feed(engine):
    session = _session(None)
    out = _submit(session, [
        {"topic": "a", "pillar": "p", "sources": [{"ref": "gh:pr-412"}]},
        {"topic": "b", "pillar": "p"},
        {"topic": "c", "pillar": "p"},
    ])
    assert out["status"] == "proposed"
    assert session.proposal.days[0]["sources"] == []
    assert "feed" not in session.proposal.strategy


def test_a_day_change_from_the_feed_moves_the_window_on_when_accepted(engine):
    from sqlmodel import Session

    from agents.content.plan_proposal import apply_proposal
    from models.content import ContentPlan

    session = _session(_digest(PR))
    with Session(engine) as db:
        row = ContentPlan(project_id=session.project_id, start_date=TODAY,
                          strategy={"mix": {"channels": []}},
                          days=[{"topic": f"t{i}", "pillar": "p"} for i in range(3)])
        db.add(row)
        db.commit()
        db.refresh(row)
        session.plan_id = row.id
    change = {"date": "2031-10-08", "topic": "Onboarding keeps GA4", "sources": [{"ref": "gh:pr-412"}]}
    out = json.loads(asyncio.run(_tool(session, "revise_plan_days").ainvoke({"changes": [change]})))
    assert out["status"] == "proposed", out
    with Session(engine) as db:
        stored = apply_proposal(db, session.proposal, now=datetime(2031, 10, 7, 9, tzinfo=timezone.utc))
        assert stored.days[1]["sources"][0]["title"] == "Retry the GA4 handshake"
        assert stored.days[0].get("sources") in (None, [])
        assert stored.strategy["feed"]["window_to"] == TODAY.isoformat()
        assert stored.strategy["mix"] == {"channels": []}


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _run(monkeypatch, engine, rows: list[dict]) -> tuple[list[dict], dict]:
    """Drive run_plan with a fake GitHub read; capture the opening turn instead
    of running a model."""
    import agents.insights.fetchers as fetchers
    from agents.content.v1.runner import ContentRunner, close_session, create_plan_session

    monkeypatch.setattr(fetchers, "fetch_entity", lambda *a, **k: {"status": "ok", "data": {"rows": rows}})
    captured: dict = {}

    async def no_model(self, session, emit, **kw):
        captured["opening"] = kw.get("opening_prompt")

    monkeypatch.setattr(ContentRunner, "_run_session", no_model)
    from sqlmodel import Session

    from models.auth import User
    from models.project import Project

    with Session(engine) as db:
        owner = User(email="o@example.com")
        db.add(owner)
        db.commit()
        project = Project(user_id=owner.id, name="Acme")
        db.add(project)
        db.commit()
        project_id, owner_id = project.id, owner.id
    runner = ContentRunner(api_key="unused-no-network")
    session = create_plan_session(str(uuid4()), project_id)
    session.user_id = owner_id
    events: list[dict] = []

    async def emit(body: dict) -> None:
        events.append(body)

    from agents.content.plan_period import requested_period

    try:
        asyncio.run(runner.run_plan(session.session_id, session.project_id, emit,
                                    period=requested_period(date.today(), 7), feed=FeedOptions()))
    finally:
        close_session(session.session_id)
    return events, captured


def _read_step(events: list[dict]) -> dict:
    (step,) = [e for e in events if e.get("event") == AgentEvent.STEP_FINISHED
               and e.get("step_id") == AgentStep.READ_WORK]
    return step["payload"]


def test_a_quiet_window_ends_the_run_with_no_model_call(monkeypatch, engine):
    quiet = [{"kind": "commit", "ref": "a" * 10, "title": "chore: tidy", "author": "maker", "at": ""}]
    events, captured = _run(monkeypatch, engine, quiet)
    payload = _read_step(events)
    assert payload["worth_a_plan"] is False and payload["left_out"] == {"chore": 1}
    assert captured == {}
    assert events[-1]["event"] == AgentEvent.PIPELINE_FINISHED and events[-1]["outcome"] == "nothing_new"


def test_a_release_opens_the_feed_turn_with_its_ref(monkeypatch, engine):
    rows = [{"kind": "release", "ref": "v1.4.0", "title": "v1.4.0", "author": "maker",
             "state": "release", "url": "https://github.com/o/r/releases/v1.4.0", "at": "2031-10-06T09:00:00Z"}]
    events, captured = _run(monkeypatch, engine, rows)
    assert _read_step(events)["items"][0]["ref"] == "gh:r-v1.4.0"
    assert "<shipped_work>" in captured["opening"] and "gh:r-v1.4.0" in captured["opening"]


def test_the_read_step_is_stored_on_the_transcript():
    """A reopened thread draws the same card: the recorder keeps the digest."""
    from agents.content.persistence import ConversationRecorder

    appended: list = []
    recorder = ConversationRecorder.__new__(ConversationRecorder)

    async def _append(kind, payload):
        appended.append((kind, payload))

    async def _track(*_a):
        return None

    recorder._append, recorder._track = _append, _track
    payload = {"worth_a_plan": False, "items": [], "left_out": {"bots": 2}}
    asyncio.run(recorder._persist({"event": AgentEvent.STEP_FINISHED, "step_id": AgentStep.READ_WORK,
                                   "payload": payload}))
    assert appended == [(EventKind.FEED, payload)]
