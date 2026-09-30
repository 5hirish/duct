"""The Daily Reflection (issue #270): the day's sources, the saved and
revised reflection, the drafts that hang off its sections, and the routes the
app reads them through.

What these pin, and why each matters:

  * every claim cites a ref the day actually contained — a reflection that
    invents a source, or cites nothing, is refused before it is saved;
  * a revision is the next version of the same artifact, and re-deriving a
    section's draft updates that post in place instead of piling up rivals;
  * a draft the person already approved is never rewritten under them;
  * a reflection run gets the reflection's tools and nothing that draws,
    plans or publishes, and no other mode gets the reflection's writers.

Fake model and SQLite throughout — no key, no network.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import agents.content.tools as content_tools
import routes.content as content_routes
import service.artifact_store as store
import service.auth as auth_service
from agents.content.reflection import (
    REFLECTION_KIND,
    ReflectionDraft,
    duct_sources,
    github_sources,
    group_for_day,
    reflection_problems,
    render_markdown,
    restore_sources,
    save_version,
    structured,
)
from agents.content.schema import ContentStatus, TEXT_POST_TYPE, make_session
from agents.content.tools import REFLECTION_TOOLS
from agents.content.v1.runner import ContentRunner, close_session, create_reflection_session
from agents.core.events import AgentEvent
from config import Configs
from db.session import get_session as get_session_dep
from models.artifact import Artifact
from models.auth import User
from models.content import ContentPost
from models.execution import ExecutionChangeSet
from models.membership import ProjectMember
from models.memory import ProjectMemory
from models.project import Project
from service import storage
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine
from tests.fakes import fake_llm

DAY = date(2026, 9, 30)
AT = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc)

GITHUB_OK = {"status": "ok", "data": {"rows": [
    {"kind": "pull_request", "ref": "#294", "title": "Run the eval on DeepSeek V4 Flash",
     "body": "Cuts a PR run from $0.25 to $0.02.", "url": "https://github.com/o/r/pull/294", "state": "merged"},
    {"kind": "commit", "ref": "aeff1d9b2c", "title": "Keep a skipped run from cancelling the eval",
     "body": "", "url": "https://github.com/o/r/commit/aeff1d9b2c", "state": ""},
]}}


def _draft(**section) -> ReflectionDraft:
    return ReflectionDraft.model_validate({
        "title": "The judge was the lenient one",
        "sections": [{
            "id": "s1", "title": "A cheaper eval",
            "happened": "Moved the eval to a model a sixth the price [gh:pr-294].",
            "field": {"url": "https://example.com/evals", "title": "Evals", "quote": "Judges drift."},
            "lesson": "A cheaper judge is only cheaper if you check it against the old one.",
            **section,
        }],
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(monkeypatch, tmp_path):
    engine = make_sqlite_engine()

    def _db():
        yield Session(engine)

    # Artifact writes open their own session; point it at this engine, and
    # their bytes at a temp dir.
    monkeypatch.setattr(store, "db_session", _db)
    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage, "get_configs", lambda: cfg)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def owner(db):
    row = User(email="builder@example.com")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Duct", slug="duct")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


def _session(project, *, sources=None):
    session = make_session(f"reflect-{uuid.uuid4()}", project.id, "reflect_day")
    session.reflection_day = DAY.isoformat()
    session.reflection_sources = sources if sources is not None else github_sources(GITHUB_OK)[0]
    return session


def _tools(session, engine, monkeypatch, emitted: list) -> dict:
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))

    async def _emit(event):
        emitted.append(event)

    return {t.name: t for t in content_tools.build_content_tools_lc(session.project_id, _emit, session)}


def _call(tool, args: dict) -> dict:
    return json.loads(asyncio.run(tool.ainvoke(args)))


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# The day's sources
# ---------------------------------------------------------------------------


def test_github_events_become_refs_the_model_can_cite():
    sources, note = github_sources(GITHUB_OK)

    assert [s["ref"] for s in sources] == ["gh:pr-294", "gh:c-aeff1d9b2c"]
    assert sources[0]["url"] == "https://github.com/o/r/pull/294" and note == ""


def test_github_missing_is_a_note_not_a_failure():
    sources, note = github_sources({"status": "not_connected", "message": "Connect GitHub."})

    assert sources == [] and "not readable" in note and "Connect GitHub." in note


def test_the_day_in_ducts_own_record_skips_reflections_and_memory_mirrors(db, project, owner):
    """A reflection is not a source for itself, and an artifact's memory
    mirror is the artifact twice."""
    other_day = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
    db.add_all([
        Artifact(project_id=project.id, group_id=uuid.uuid4(), kind="brief", slug="organic-slip",
                 title="Organic slip", created_at=AT),
        Artifact(project_id=project.id, group_id=uuid.uuid4(), kind=REFLECTION_KIND, slug="reflection-2026-09-30",
                 title="Yesterday", created_at=AT),
        Artifact(project_id=project.id, group_id=uuid.uuid4(), kind="brief", slug="older", title="Older",
                 created_at=other_day),
        ExecutionChangeSet(user_id=owner.id, project_id=project.id, connector_type="google_ads",
                           title="Shift budget to brand", status="applied", updated_at=AT),
        ProjectMemory(scope="project", project_id=project.id, kind="insight", title="Brand terms convert",
                      recorded_at=AT, observed_at=AT, valid_from=AT),
        ProjectMemory(scope="project", project_id=project.id, kind="artifact", title="Organic slip",
                      recorded_at=AT, observed_at=AT, valid_from=AT),
    ])
    db.commit()

    kinds = {(s["kind"], s["title"].split(" (")[0]) for s in duct_sources(db, project.id, DAY)}

    assert kinds == {
        ("artifact", "Organic slip"), ("change_set", "Shift budget to brand"), ("memory", "Brand terms convert"),
    }


# ---------------------------------------------------------------------------
# What the model writes
# ---------------------------------------------------------------------------


def test_a_claim_must_cite_a_ref_the_day_contained():
    known = {"gh:pr-294"}

    assert reflection_problems(_draft(), known) == []
    uncited = reflection_problems(_draft(happened="Moved the eval to a cheaper model."), known)
    invented = reflection_problems(_draft(happened="Shipped it [gh:pr-999]."), known)
    assert "cites nothing" in uncited[0]
    assert "gh:pr-999 is not in today's sources" in invented[0]


def test_citations_render_as_links_and_the_sources_come_back_on_resume():
    sources, _ = github_sources(GITHUB_OK)

    markdown = render_markdown(_draft(), DAY, sources)
    day, restored = restore_sources(structured(_draft(), DAY, sources))

    assert "[gh:pr-294](https://github.com/o/r/pull/294)" in markdown
    assert "> Judges drift." in markdown
    assert day == "2026-09-30" and {s["ref"] for s in restored} == {s["ref"] for s in sources}


def test_a_revision_is_the_next_version_of_the_same_reflection(db, project, owner):
    sources, _ = github_sources(GITHUB_OK)
    v1 = save_version(db, project_id=project.id, user_id=owner.id, conversation_id=None,
                      group_id=None, draft=_draft(), day=DAY, sources=sources)
    v2 = save_version(db, project_id=project.id, user_id=owner.id, conversation_id=None,
                      group_id=v1.group_id, draft=_draft(lesson="Check the judge first."), day=DAY, sources=sources)

    assert (v1.version, v2.version) == (1, 2) and v2.group_id == v1.group_id
    assert v2.kind == REFLECTION_KIND and v2.structured_json["sections"][0]["lesson"] == "Check the judge first."
    assert group_for_day(db, project.id, DAY) == v1.group_id


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------


def test_a_reflection_run_gets_its_tools_and_no_writer_that_draws_or_publishes(project, engine, monkeypatch):
    reflect = set(_tools(_session(project), engine, monkeypatch, []))
    draft = set(_tools(make_session("d", project.id, "draft_post"), engine, monkeypatch, []))

    assert reflect == set(REFLECTION_TOOLS)
    assert not {"save_reflection", "draft_from_section"} & draft
    assert {"publish_post", "submit_post_draft"} <= draft


def test_saving_twice_revises_and_the_drafts_follow_their_section(db, project, engine, monkeypatch):
    session = _session(project)
    emitted: list = []
    tools = _tools(session, engine, monkeypatch, emitted)

    saved = _call(tools["save_reflection"], {"reflection": _draft().model_dump()})
    first = _call(tools["draft_from_section"], {"section_id": "s1", "channel": "twitter", "caption": "Cheaper judge, same verdicts."})
    revised = _call(tools["save_reflection"], {"reflection": _draft(lesson="Check the judge.").model_dump() | {"label": "Sharper lesson"}})
    again = _call(tools["draft_from_section"], {"section_id": "s1", "channel": "twitter", "caption": "Check the judge first."})
    linkedin = _call(tools["draft_from_section"], {"section_id": "s1", "channel": "linkedin", "caption": "A longer take."})

    assert saved["status"] == "ok" and revised["version"] == 2 and revised["group_id"] == saved["group_id"]
    assert first["post_id"] == again["post_id"] and again["updated"] is True
    assert linkedin["post_id"] != first["post_id"]
    post = db.get(ContentPost, uuid.UUID(first["post_id"]))
    assert post.caption == "Check the judge first." and post.post_type == TEXT_POST_TYPE
    assert post.status == ContentStatus.PENDING
    assert post.reflection == {"group_id": saved["group_id"], "section_id": "s1", "date": "2026-09-30"}
    versions = [e for e in emitted if e["event"] == AgentEvent.ARTIFACT_VERSION]
    assert [v["payload"]["version"] for v in versions] == [1, 2]
    assert versions[0]["payload"]["reflection"]["sections"][0]["id"] == "s1"


def test_an_uncited_reflection_and_a_draft_before_it_are_refused(project, engine, monkeypatch):
    tools = _tools(_session(project), engine, monkeypatch, [])

    early = _call(tools["draft_from_section"], {"section_id": "s1", "channel": "twitter", "caption": "Hi."})
    uncited = _call(tools["save_reflection"], {"reflection": _draft(happened="We shipped.").model_dump()})

    assert early["status"] == "error" and "Save the reflection first" in early["message"]
    assert uncited["status"] == "error" and "cites nothing" in uncited["message"]


def test_an_approved_draft_is_left_as_it_is(db, project, engine, monkeypatch):
    tools = _tools(_session(project), engine, monkeypatch, [])
    _call(tools["save_reflection"], {"reflection": _draft().model_dump()})
    made = _call(tools["draft_from_section"], {"section_id": "s1", "channel": "twitter", "caption": "Out."})
    post = db.get(ContentPost, uuid.UUID(made["post_id"]))
    post.status = ContentStatus.SCHEDULED
    db.add(post)
    db.commit()

    refused = _call(tools["draft_from_section"], {"section_id": "s1", "channel": "twitter", "caption": "Changed."})

    assert refused["status"] == "error" and "already scheduled" in refused["message"]
    db.refresh(post)
    assert post.caption == "Out."


def test_an_over_length_tweet_from_a_section_is_refused(project, engine, monkeypatch):
    tools = _tools(_session(project), engine, monkeypatch, [])
    _call(tools["save_reflection"], {"reflection": _draft().model_dump()})

    refused = _call(tools["draft_from_section"], {"section_id": "s1", "channel": "twitter", "caption": "x" * 281})

    assert refused["status"] == "error" and "allows 280" in refused["message"]


# ---------------------------------------------------------------------------
# The session and the routes
# ---------------------------------------------------------------------------


async def test_the_finish_event_carries_the_reflection_the_workspace_opens(project):
    session = create_reflection_session(str(uuid.uuid4()), project.id)
    session.reflection_group_id = uuid.uuid4()   # what save_reflection stashes
    emitted: list = []

    async def _emit(event):
        emitted.append(event)

    try:
        await ContentRunner(api_key="unused")._run_session(
            session, _emit, system_prompt="sys", opening_prompt="reflect",
            llm=fake_llm("Saved."), chat_idle_timeout=0.2, resume=False,
        )
    finally:
        close_session(session.session_id)

    finished = next(e for e in emitted if e["event"] == AgentEvent.PIPELINE_FINISHED)
    assert finished["reflection_group_id"] == str(session.reflection_group_id)
    assert finished["mode"] == "reflect_day"


def test_the_journal_and_one_day_read_back_with_their_drafts(db, project, owner, engine, monkeypatch):
    tools = _tools(_session(project), engine, monkeypatch, [])
    saved = _call(tools["save_reflection"], {"reflection": _draft().model_dump()})
    _call(tools["draft_from_section"], {"section_id": "s1", "channel": "twitter", "caption": "Cheaper judge."})
    api = _api(db, owner)

    journal = api.get(f"/api/content/reflections?project_id={project.id}").json()
    one = api.get(f"/api/content/reflections/{saved['group_id']}").json()

    assert journal[0]["day"] == "2026-09-30" and journal[0]["drafts"] == 1 and journal[0]["waiting"] == 1
    assert one["reflection"]["sections"][0]["id"] == "s1" and one["version"] == 1
    assert "[gh:pr-294](https://github.com/o/r/pull/294)" in one["content"]
    assert one["drafts"][0]["reflection"]["section_id"] == "s1"


def test_a_stranger_cannot_read_a_reflection(db, project, engine, monkeypatch):
    tools = _tools(_session(project), engine, monkeypatch, [])
    saved = _call(tools["save_reflection"], {"reflection": _draft().model_dump()})
    stranger = User(email="stranger@example.com")
    db.add(stranger)
    db.commit()

    assert _api(db, stranger).get(f"/api/content/reflections/{saved['group_id']}").status_code == 404
    assert _api(db, stranger).get(f"/api/content/reflections?project_id={project.id}").status_code == 404
