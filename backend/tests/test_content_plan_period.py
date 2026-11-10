"""A plan manages a period: its dates, one post per date, and revising it
changes that plan rather than leaving a second one beside it."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from uuid import uuid4

import pytest

from agents.content.plan_period import (
    MAX_PLAN_DAYS,
    PlanPeriod,
    default_period,
    keep_drafted_days,
    link_post_to_day,
    requested_period,
)

# ---------------------------------------------------------------------------
# The period
# ---------------------------------------------------------------------------


def test_the_default_is_the_rest_of_the_month_from_today():
    period = default_period(date(2026, 10, 7))
    assert period.start == date(2026, 10, 7)
    assert period.end == date(2026, 10, 31)
    assert period.days == 25


def test_the_last_days_of_a_month_roll_over_to_the_next():
    assert default_period(date(2026, 10, 25)).end == date(2026, 10, 31)  # a week left: still October
    period = default_period(date(2026, 10, 26))
    assert (period.start, period.end) == (date(2026, 11, 1), date(2026, 11, 30))


def test_a_period_is_never_longer_than_the_cap():
    # October from the 1st is 31 days; the plan stops at the 30th.
    assert default_period(date(2026, 10, 1)).days == MAX_PLAN_DAYS
    with pytest.raises(ValueError):
        requested_period(date(2026, 11, 1), MAX_PLAN_DAYS + 1)


def test_a_picked_length_counts_from_its_start():
    week = requested_period(date(2026, 10, 7), 7)
    assert (week.start, week.end) == (date(2026, 10, 7), date(2026, 10, 13))
    assert week.label() == "Oct 7 – Oct 13, 2026"
    month = requested_period(date(2026, 11, 1))
    assert (month.end, month.label()) == (date(2026, 11, 30), "November 2026")


def test_a_revision_keeps_the_days_that_have_a_draft():
    old = [{"topic": "a", "pillar": "p", "post_id": "x"}, {"topic": "b", "pillar": "p"}]
    new = [{"topic": "A", "pillar": "p"}, {"topic": "B", "pillar": "p"}]
    merged, kept = keep_drafted_days(old, new)
    assert merged[0]["topic"] == "a" and merged[0]["post_id"] == "x"
    assert merged[1]["topic"] == "B"
    assert kept == [0]


def test_a_day_is_linked_to_its_post_once():
    days = [{"topic": "a"}, {"topic": "b", "status": "pending"}]
    linked = link_post_to_day(days, 1, "p1")
    assert linked[1] == {"topic": "b", "status": "draft", "post_id": "p1"}
    assert linked[0] is days[0] and "post_id" not in days[1]   # the input is not mutated
    assert link_post_to_day(linked, 1, "p1") is None            # already linked: nothing to write
    assert link_post_to_day(days, 5, "p1") is None              # no such day


# ---------------------------------------------------------------------------
# submit_plan: one plan per period
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(monkeypatch):
    from tests.conftest import make_sqlite_engine

    import agents.content.tools as content_tools
    import db.session as db_session

    eng = make_sqlite_engine()
    monkeypatch.setattr(db_session, "get_engine", lambda: eng)
    monkeypatch.setattr(content_tools, "get_engine", lambda: eng)
    return eng


def _submit(session, days: list[dict]) -> dict:
    from agents.content.tools import build_content_tools_lc

    async def emit(_body: dict) -> None:
        return None

    tool = {t.name: t for t in build_content_tools_lc(session.project_id, emit, session)}["submit_plan"]
    plan = {"type": "plan", "project_id": str(session.project_id), "days": days}
    return json.loads(asyncio.run(tool.ainvoke({"plan": plan})))


def _days(n: int, topic: str = "t") -> list[dict]:
    return [{"topic": f"{topic}{i}", "pillar": "p"} for i in range(n)]


def _plans(engine) -> list:
    from sqlmodel import Session, select

    from models.content import ContentPlan

    with Session(engine) as db:
        return db.execute(select(ContentPlan)).scalars().all()


def _accept(engine, session, now=None):
    """What the accept route does once the person clicks: write the proposal."""
    from sqlmodel import Session

    from agents.content.plan_proposal import apply_proposal
    from utils.dates import utcnow

    with Session(engine) as db:
        row = apply_proposal(db, session.proposal, now=now or utcnow())
        session.plan_id, session.proposal = row.id, None
        return row


def test_a_submit_proposes_and_writes_nothing_until_accepted(engine):
    """The agent's plan is a proposal on the session, shown with Accept /
    Modify / Reject; a second submit replaces the proposal, and only Accept
    makes a row. Until 2026-11-08 the first call wrote thirty days to the
    board with nobody asked."""
    from agents.content.schema import make_session

    session = make_session("s", uuid4(), "plan_month")
    # A period ahead of any real "today": Accept keeps days already past, and
    # this test is about replacement, not the cutoff.
    session.period_start, session.period_days = date(2031, 10, 7), 3
    first = _submit(session, _days(3, "first"))
    assert first["status"] == "proposed" and first["plan_id"] == ""
    assert _plans(engine) == []
    second = _submit(session, _days(3, "second"))
    assert second["status"] == "proposed"
    assert [d["topic"] for d in session.proposal.days] == ["second0", "second1", "second2"]

    row = _accept(engine, session)
    (stored,) = _plans(engine)
    assert stored.id == row.id and stored.start_date == date(2031, 10, 7)
    assert [d["topic"] for d in stored.days] == ["second0", "second1", "second2"]
    # The next submit in the same session proposes against the accepted plan.
    third = _submit(session, _days(3, "third"))
    assert third["replaces_plan_id"] == str(row.id)
    _accept(engine, session)
    (stored,) = _plans(engine)
    assert stored.id == row.id and [d["topic"] for d in stored.days] == ["third0", "third1", "third2"]


def test_the_proposal_carries_the_mix_the_plan_was_made_from(engine):
    from agents.content.channel_mix import Goal, GoalKind, build_mix
    from agents.content.schema import make_session

    session = make_session("s", uuid4(), "plan_month")
    session.period_start, session.period_days = date(2031, 10, 7), 3
    session.channel_mix = build_mix([], ["tiktok", "linkedin"], Goal(GoalKind.INTENT), 3, None)
    _submit(session, _days(3))
    mix = session.proposal.strategy["mix"]
    assert [c["channel"] for c in mix["channels"]] == ["tiktok", "linkedin"]
    assert _accept(engine, session).strategy["mix"] == mix


def test_a_proposal_on_a_live_plan_keeps_drafted_days_and_the_past(engine):
    """Accept replaces the plan from today on: a drafted day stays because the
    board finds the draft through it, and a day before today stays because
    it already happened. The proposal says which indexes it kept."""
    from sqlmodel import Session

    from agents.content.schema import make_session
    from models.content import ContentPlan

    project = uuid4()
    start = date(2026, 10, 1)
    with Session(engine) as db:
        row = ContentPlan(project_id=project, start_date=start,
                          days=[{"topic": "past", "pillar": "p"},
                                {"topic": "drafted", "pillar": "p", "post_id": str(uuid4())},
                                {"topic": "old", "pillar": "p"}])
        db.add(row)
        db.commit()
        db.refresh(row)
        plan_id = row.id
    session = make_session("s", project, "plan_month")
    session.plan_id, session.period_start, session.period_days = plan_id, start, 3

    from agents.content import tools as content_tools
    from datetime import datetime, timezone

    # Today is day index 1, so index 0 is the past.
    today = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    content_tools.utcnow = lambda: today  # type: ignore[assignment]
    try:
        result = _submit(session, _days(3, "new"))
    finally:
        from utils.dates import utcnow as real_utcnow
        content_tools.utcnow = real_utcnow  # type: ignore[assignment]
    assert result["kept_days"] == [0, 1]
    assert [d["topic"] for d in session.proposal.days] == ["past", "drafted", "new2"]

    _accept(engine, session, now=today)
    (stored,) = _plans(engine)
    assert stored.id == plan_id
    assert [d["topic"] for d in stored.days] == ["past", "drafted", "new2"]


def test_accept_merges_against_the_plan_as_it_is_by_then(engine):
    """A proposal can wait days now (it is held on the conversation), and the
    plan moves meanwhile: a day drafted, or gone by, while it waited stays."""
    from datetime import datetime, timezone

    from sqlmodel import Session

    from agents.content.schema import make_session
    from models.content import ContentPlan

    project, start = uuid4(), date(2031, 10, 1)
    with Session(engine) as db:
        row = ContentPlan(project_id=project, start_date=start, days=_days(3, "old"))
        db.add(row)
        db.commit()
        db.refresh(row)
        plan_id = row.id
    session = make_session("s", project, "plan_month")
    session.plan_id, session.period_start, session.period_days = plan_id, start, 3
    _submit(session, _days(3, "new"))

    drafted = str(uuid4())
    with Session(engine) as db:
        row = db.get(ContentPlan, plan_id)
        row.days = [row.days[0], row.days[1], {**row.days[2], "post_id": drafted}]
        db.add(row)
        db.commit()
    _accept(engine, session, now=datetime(2031, 10, 2, 9, tzinfo=timezone.utc))
    (stored,) = _plans(engine)
    assert [d["topic"] for d in stored.days] == ["old0", "new1", "old2"]
    assert stored.days[2]["post_id"] == drafted


def test_a_proposal_is_held_on_its_conversation_until_the_person_decides(engine):
    from sqlmodel import Session

    from agents.content.plan_proposal import HELD_PROPOSAL_KEY, held_proposal, hold_proposal
    from agents.content.schema import make_session
    from models.content.conversation import AgentConversation

    project = uuid4()
    with Session(engine) as db:
        conv = AgentConversation(agent_type="tiktok_studio", project_id=project, mode="plan_month")
        db.add(conv)
        db.commit()
        conv_id = conv.id
    session = make_session("s", project, "plan_month")
    session.conversation_id = conv_id
    session.period_start, session.period_days = date(2031, 10, 7), 3
    _submit(session, _days(3, "kept"))

    with Session(engine) as db:
        held = held_proposal(db, conv_id)
        assert held == session.proposal, "the same proposal, round-tripped"

    # The person decides: the conversation lets go of it and says what they chose.
    from agents.content.persistence import load_events
    from routes.content import _record_plan_decision

    with Session(engine) as db:
        _record_plan_decision(db, session, held, "rejected")
        assert HELD_PROPOSAL_KEY not in db.get(AgentConversation, conv_id).meta
        (decision,) = load_events(db, conv_id)
        assert (decision.kind, decision.data["decision"]) == ("plan_decision", "rejected")
        hold_proposal(db, conv_id, held)
        assert held_proposal(db, conv_id) == held


def test_a_plan_built_on_one_unproven_hook_is_refused(engine):
    from agents.content.schema import make_session

    session = make_session("s", uuid4(), "plan_month")
    session.period_start, session.period_days = date(2031, 10, 7), 8
    days = [{**d, "hook_type": "transformation_reveal" if i < 3 else f"hook{i}"} for i, d in enumerate(_days(8))]
    result = _submit(session, days)
    assert result["status"] == "error" and "transformation_reveal is on 3 of tiktok's 8 days" in result["message"]
    assert session.proposal is None


def test_a_day_on_a_channel_the_brand_does_not_post_on_is_refused(engine):
    from agents.content.schema import make_session

    session = make_session("s", uuid4(), "plan_month")
    session.period_start, session.period_days = date(2026, 10, 7), 1
    session.active_channels = ["tiktok", "instagram"]
    result = _submit(session, [{"topic": "t", "pillar": "p", "platforms": ["linkedin"]}])
    assert result["status"] == "error" and "linkedin" in result["message"]
    assert session.proposal is None


def test_merge_proposal_is_an_index_cutoff_on_the_calendar():
    """No database: the merge is data. Positions are dates, so 'before today'
    is an index, and a drafted day wins wherever it sits."""
    from agents.content.plan_proposal import merge_proposal

    old = [{"topic": "a"}, {"topic": "b", "post_id": "x"}, {"topic": "c"}, {"topic": "d"}]
    new = [{"topic": f"n{i}"} for i in range(4)]
    merged, kept = merge_proposal(old, new, start=date(2026, 10, 1), today=date(2026, 10, 3))
    assert [d["topic"] for d in merged] == ["a", "b", "n2", "n3"]
    assert kept == [0, 1]
    # Nothing live: the proposal whole, nothing kept.
    merged, kept = merge_proposal(None, new, start=date(2026, 10, 1), today=date(2026, 10, 3))
    assert [d["topic"] for d in merged] == ["n0", "n1", "n2", "n3"] and kept == []


def test_a_plan_must_cover_its_period_exactly(engine):
    from agents.content.schema import make_session

    session = make_session("s", uuid4(), "plan_month")
    session.period_start, session.period_days = date(2026, 10, 7), 25

    result = _submit(session, _days(30))

    assert result["status"] == "error" and "exactly 25 days" in result["message"]
    assert _plans(engine) == []


# ---------------------------------------------------------------------------
# Which plan a run manages
# ---------------------------------------------------------------------------


def test_a_run_manages_the_plan_already_covering_today(engine):
    from sqlmodel import Session

    from agents.content.schema import make_session
    from agents.content.v1.runner import _resolve_plan_period
    from models.content import ContentPlan

    project = uuid4()
    today = date(2026, 10, 7)
    with Session(engine) as db:
        current = ContentPlan(project_id=project, start_date=date(2026, 10, 1), days=_days(30))
        db.add(current)
        db.commit()
        db.refresh(current)

    session = make_session("s", project, "plan_month")
    days = _resolve_plan_period(session, None, today)

    assert session.plan_id == current.id
    assert days is not None and len(days) == 30
    assert (session.period_start, session.period_days) == (date(2026, 10, 1), 30)


def test_a_run_with_no_plan_for_its_dates_makes_one_for_them(engine):
    from sqlmodel import Session

    from agents.content.schema import make_session
    from agents.content.v1.runner import _resolve_plan_period
    from models.content import ContentPlan

    project = uuid4()
    with Session(engine) as db:
        db.add(ContentPlan(project_id=project, start_date=date(2026, 9, 1), days=_days(30)))
        db.commit()

    session = make_session("s", project, "plan_month")
    assert _resolve_plan_period(session, None, date(2026, 10, 7)) is None
    assert session.plan_id is None
    assert (session.period_start, session.period_days) == (date(2026, 10, 7), 25)

    nxt = make_session("n", project, "plan_month")
    picked = PlanPeriod(date(2026, 11, 1), 30)
    assert _resolve_plan_period(nxt, picked, date(2026, 10, 7)) is None
    assert nxt.period_start == date(2026, 11, 1) and nxt.period_days == 30
    assert picked.end == date(2026, 11, 1) + timedelta(days=29)


def test_a_new_plan_stops_short_of_the_next_one(engine):
    from sqlmodel import Session

    from agents.content.schema import make_session
    from agents.content.v1.runner import _resolve_plan_period
    from models.content import ContentPlan

    project = uuid4()
    with Session(engine) as db:
        db.add(ContentPlan(project_id=project, start_date=date(2026, 10, 20), days=_days(7)))
        db.commit()

    session = make_session("s", project, "plan_month")
    assert _resolve_plan_period(session, PlanPeriod(date(2026, 10, 7), 30), date(2026, 10, 7)) is None
    assert (session.period_start, session.period_days) == (date(2026, 10, 7), 13)


def test_a_rolled_over_month_is_managed_when_it_already_has_a_plan(engine):
    from sqlmodel import Session

    from agents.content.schema import make_session
    from agents.content.v1.runner import _resolve_plan_period
    from models.content import ContentPlan

    project = uuid4()
    with Session(engine) as db:
        november = ContentPlan(project_id=project, start_date=date(2026, 11, 1), days=_days(30))
        db.add(november)
        db.commit()
        db.refresh(november)

    session = make_session("s", project, "plan_month")
    assert _resolve_plan_period(session, None, date(2026, 10, 28)) is not None
    assert session.plan_id == november.id


def test_a_draft_for_a_plan_day_fills_the_day_as_soon_as_it_is_saved(engine):
    """The board finds a day's draft through the day's ``post_id``. It used to
    be written when the drafting chat ended, so a chat cut off by a server
    restart left a saved draft the board never showed (2026-11-08)."""
    from sqlmodel import Session

    from agents.content.schema import make_session
    from agents.content.tools import build_content_tools_lc
    from models.auth import User
    from models.content import ContentPlan, ContentPost
    from models.project import Project

    with Session(engine) as db:
        user = User(email="planner@example.com")
        db.add(user)
        db.commit()
        project = Project(user_id=user.id, name="Kestrel Studio", slug="kestrel")
        db.add(project)
        db.commit()
        project_id = project.id

    planning = make_session("plan", project_id, "plan_month")
    planning.period_start, planning.period_days = date(2031, 10, 7), 3
    _submit(planning, _days(3))
    plan = _accept(engine, planning)

    drafting = make_session("draft", project_id, "draft_post")
    drafting.channel = "twitter"
    drafting.plan_id, drafting.day_index = plan.id, 1

    async def emit(_body: dict) -> None:
        return None

    tool = {t.name: t for t in build_content_tools_lc(project_id, emit, drafting)}["submit_post_draft"]
    draft = {
        "type": "post", "project_id": str(project_id), "post_dir_slug": "2031-10-08-001",
        "pillar": "p", "topic": "t1", "caption": "Shipped the eval gate. It failed us twice.",
    }
    result = json.loads(asyncio.run(tool.ainvoke({"post": draft})))
    assert result.get("status") != "error", result

    with Session(engine) as db:
        days = db.get(ContentPlan, plan.id).days
        assert days[1]["post_id"] == str(drafting.post_id) and days[1]["status"] == "draft"
        assert not days[0].get("post_id") and not days[2].get("post_id")
        assert db.get(ContentPost, drafting.post_id).plan_id == plan.id


def test_a_drafts_conversation_is_tied_to_the_post_when_the_post_is_born(engine):
    """Opening a draft resumes its chat through this link; it used to be
    written when the chat ended, so a cut-off chat reopened as a new one."""
    from sqlmodel import Session

    from agents.content.persistence import find_active_conversation
    from agents.content.schema import make_session
    from agents.content.tools import build_content_tools_lc
    from models.auth import User
    from models.content.conversation import AgentConversation
    from models.project import Project

    with Session(engine) as db:
        user = User(email="writer@example.com")
        db.add(user)
        db.commit()
        project = Project(user_id=user.id, name="Kestrel Studio", slug="kestrel")
        db.add(project)
        db.commit()
        conv = AgentConversation(agent_type="tiktok_studio", project_id=project.id, user_id=user.id)
        db.add(conv)
        db.commit()
        project_id, conv_id = project.id, conv.id

    drafting = make_session("draft", project_id, "draft_post")
    drafting.channel, drafting.conversation_id = "twitter", conv_id

    async def emit(_body: dict) -> None:
        return None

    tool = {t.name: t for t in build_content_tools_lc(project_id, emit, drafting)}["submit_post_draft"]
    draft = {
        "type": "post", "project_id": str(project_id), "post_dir_slug": "2031-10-08-002",
        "pillar": "p", "topic": "t", "caption": "Shipped the eval gate. It failed us twice.",
    }
    assert json.loads(asyncio.run(tool.ainvoke({"post": draft}))).get("status") != "error"

    with Session(engine) as db:
        found = find_active_conversation(db, artifact_type="post", artifact_id=drafting.post_id, project_id=project_id)
        assert found is not None and found.id == conv_id
