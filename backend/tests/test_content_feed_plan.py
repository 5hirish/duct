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
              url="https://github.com/o/r/pull/412", raw="#412")
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
        {"topic": "Onboarding keeps GA4", "pillar": "Product", "sources": [{"ref": "gh:pr-412", "title": "x"}],
         "brief": {"idea": "Keep GA4 connected through a blip", "evidence": ["retries the handshake [gh:pr-412]"]}},
        {"topic": "t1", "pillar": "p"},
        {"topic": "t2", "pillar": "p"},
    ])
    assert out["status"] == "proposed", out
    first = session.proposal.days[0]
    assert first["sources"] == [{"ref": "gh:pr-412", "kind": "pull_request", "raw": "#412",
                                 "title": "Retry the GA4 handshake", "url": "https://github.com/o/r/pull/412"}]
    assert first["brief"]["evidence"] == ["retries the handshake [gh:pr-412]"]
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
        {"topic": "a", "pillar": "p", "sources": [{"ref": "gh:pr-412"}], "brief": {"idea": "Keep GA4 connected through a blip", "evidence": ["retries the handshake [gh:pr-412]"]}},
        {"topic": "b", "pillar": "p"},
        {"topic": "c", "pillar": "p"},
    ])
    assert out["status"] == "proposed"
    assert session.proposal.days[0]["sources"] == []
    assert session.proposal.days[0]["brief"]["evidence"] == []
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
    change = {"date": "2031-10-08", "topic": "Onboarding keeps GA4", "sources": [{"ref": "gh:pr-412"}],
              "brief": {"idea": "Keep GA4 connected through a blip", "evidence": ["retries the handshake [gh:pr-412]"]}}
    out = json.loads(asyncio.run(_tool(session, "revise_plan_days").ainvoke({"changes": [change]})))
    assert out["status"] == "proposed", out
    with Session(engine) as db:
        stored = apply_proposal(db, session.proposal, now=datetime(2031, 10, 7, 9, tzinfo=timezone.utc))
        assert stored.days[1]["sources"][0]["title"] == "Retry the GA4 handshake"
        assert stored.days[1]["brief"]["idea"] == "Keep GA4 connected through a blip"
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


# ---------------------------------------------------------------------------
# The handoff to the writer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("channel", ["linkedin", "tiktok"])
def test_the_writer_of_a_feed_day_gets_the_story_the_plan_read(channel):
    """The draft runs days later in its own session and cannot open what the
    plan read; until 2026-11-24 it got only the topic and guessed the story."""
    from agents.content.channels import resolve
    from agents.content.prompts import build_post_revise_prompt, build_post_user_prompt
    from agents.content.schema import ContentBrandContext, Day

    brand = ContentBrandContext(project_id=uuid4(), project_name="Acme")
    day = Day.model_validate({
        "topic": "Keep GA4 connected", "pillar": "Product", "platforms": [channel],
        "sources": [{"ref": "gh:pr-412", "title": "Retry the GA4 handshake", "url": "https://github.com/o/r/pull/412"}],
        "brief": {"idea": "A dropped GA4 link fixes itself", "evidence": ["retries three times [gh:pr-412]"],
                  "ask": "npx getduct check"},
    })
    for prompt in (build_post_user_prompt(brand, day, channel=resolve(channel)),
                   build_post_revise_prompt(brand, day, channel=resolve(channel))):
        assert "<story_brief>" in prompt
        assert "A dropped GA4 link fixes itself" in prompt and "retries three times [gh:pr-412]" in prompt
        assert "https://github.com/o/r/pull/412" in prompt

    plain = Day.model_validate({"topic": "Keep GA4 connected", "pillar": "Product", "platforms": [channel]})
    assert "<story_brief>" not in build_post_user_prompt(brand, plain, channel=resolve(channel))


def test_what_a_plan_left_out_is_kept_and_the_next_feed_shows_it_marked(engine):
    """The reasons a plan gave for leaving items out used to live only in
    chat, so the next run offered them again as new."""
    from agents.content.feed import build_digest, render_digest, set_aside_refs

    session = _session(_digest(PR, RELEASE))
    plan = {"type": "plan", "project_id": str(session.project_id),
            "days": [{"topic": "t0", "pillar": "p"}, {"topic": "t1", "pillar": "p"}, {"topic": "t2", "pillar": "p"}],
            "set_aside": [{"ref": "gh:r-v1.4.0", "why": "announcement only"}, {"ref": "gh:pr-999", "why": "x"}]}
    out = json.loads(asyncio.run(_tool(session, "submit_plan").ainvoke({"plan": plan})))
    assert out["status"] == "proposed", out
    assert session.proposal.strategy["feed"]["set_aside"] == [{"ref": "gh:r-v1.4.0", "why": "announcement only"}]

    stored = type("P", (), {"strategy": session.proposal.strategy, "days": []})()
    aside = set_aside_refs([stored])
    release = FeedItem(ref="gh:r-v1.4.0", kind="release", title="v1.4.0")
    digest = build_digest(FeedOptions(), (TODAY, TODAY), github_rows=None, duct=[release], already=set(),
                          set_aside=aside)
    assert "[set aside before: announcement only]" in render_digest(digest)


def test_a_day_renamed_outside_a_feed_plan_drops_the_story_it_no_longer_tells(engine):
    from sqlmodel import Session

    from models.content import ContentPlan

    session = _session(None)
    sourced = {"topic": "Keep GA4 connected", "pillar": "p", "sources": [{"ref": "gh:pr-412"}],
               "brief": {"idea": "A dropped GA4 link fixes itself", "evidence": ["x [gh:pr-412]"]}}
    with Session(engine) as db:
        row = ContentPlan(project_id=session.project_id, start_date=TODAY,
                          days=[dict(sourced), dict(sourced), {"topic": "t2", "pillar": "p"}])
        db.add(row)
        db.commit()
        db.refresh(row)
        session.plan_id = row.id
    changes = [{"date": "2031-10-07", "topic": "Something else entirely"},
               {"date": "2031-10-08", "post_type": "text"}]
    out = json.loads(asyncio.run(_tool(session, "revise_plan_days").ainvoke({"changes": changes})))
    assert out["status"] == "proposed", out
    renamed, kept = session.proposal.days[0], session.proposal.days[1]
    assert renamed["sources"] == [] and renamed["brief"]["idea"] == ""
    assert kept["sources"] and kept["brief"]["idea"] == "A dropped GA4 link fixes itself"


def test_a_day_s_own_sources_open_again_for_its_writer():
    from agents.content.feed import story_digest
    from agents.content.feed_read import read_shipped

    digest = story_digest([
        {"ref": "gh:pr-412", "kind": "pull_request", "title": "Retry", "raw": "#412"},
        {"ref": "gh:r-v1.4.0", "title": "v1.4.0"},       # saved before `raw` was kept
        {"ref": "mem:abc", "title": "a memory"},          # nothing to open again
    ], visibility="public")
    assert {i.ref: (i.kind, i.raw) for i in digest.items} == {
        "gh:pr-412": ("pull_request", "#412"), "gh:r-v1.4.0": ("release", "v1.4.0"),
    }
    assert digest.public
    assert story_digest([{"ref": "mem:abc"}]) is None
    refused = read_shipped(digest, "gh:pr-999", user_id=None, project_id=None)
    assert refused["status"] == "not_in_feed"


def test_a_draft_s_kickoff_lists_the_project_s_recent_posts(engine):
    from sqlmodel import Session

    from agents.content.schema import ContentStatus
    from agents.content.v1.runner import _recent_posts
    from models.content import ContentPost

    project_id = uuid4()
    with Session(engine) as db:
        for n, status in enumerate((ContentStatus.DRAFT, ContentStatus.PENDING, ContentStatus.POSTED)):
            db.add(ContentPost(project_id=project_id, post_dir_slug=f"2031-10-0{n + 1}-001",
                               topic=f"topic {n}", pillar="p", status=status))
        db.commit()
    assert [p["topic"] for p in _recent_posts(project_id)] in (["topic 0", "topic 2"], ["topic 2", "topic 0"])


@pytest.mark.parametrize("language", ["Spanish", ""])
def test_the_brand_s_content_language_governs_every_content_prompt(language):
    from agents.content.prompts import _brand_stanza
    from agents.content.schema import ContentBrandContext

    stanza = _brand_stanza(ContentBrandContext(project_id=uuid4(), project_name="Acme", content_language=language))
    assert ("Write all content in Spanish" in stanza) is bool(language)
