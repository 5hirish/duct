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


def test_a_second_submit_revises_the_same_plan(engine):
    from agents.content.schema import make_session

    session = make_session("s", uuid4(), "plan_month")
    session.period_start, session.period_days = date(2026, 10, 7), 3

    first = _submit(session, _days(3, "first"))
    second = _submit(session, _days(3, "second"))

    assert first["plan_id"] == second["plan_id"]
    (row,) = _plans(engine)
    assert row.start_date == date(2026, 10, 7)
    assert [d["topic"] for d in row.days] == ["second0", "second1", "second2"]


def test_a_revision_leaves_drafted_days_alone_and_says_so(engine):
    from sqlmodel import Session

    from agents.content.schema import make_session
    from models.content import ContentPlan

    project = uuid4()
    with Session(engine) as db:
        row = ContentPlan(project_id=project, start_date=date(2026, 10, 1),
                          days=[{"topic": "drafted", "pillar": "p", "post_id": str(uuid4())},
                                {"topic": "old", "pillar": "p"}])
        db.add(row)
        db.commit()
        db.refresh(row)
        plan_id = row.id

    session = make_session("s", project, "plan_month")
    session.plan_id, session.period_start, session.period_days = plan_id, date(2026, 10, 1), 2

    result = _submit(session, _days(2, "new"))

    assert result["kept_days"] == [0]
    (row,) = _plans(engine)
    assert row.id == plan_id
    assert [d["topic"] for d in row.days] == ["drafted", "new1"]


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
