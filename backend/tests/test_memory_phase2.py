"""Phase 2 memory: consolidation, the pause switch, preferences, controls.

Covers only what Phase 2 added. The table, supersession, search, digest and the
Phase 1 routes are exercised in tests/test_memory.py and are not repeated here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.core.events import EventKind  # noqa: E402
from agents.preferences import UserPreferences  # noqa: E402
from db.session import get_session as get_session_dep  # noqa: E402
from models.auth import User  # noqa: E402
from models.content.conversation import AgentConversation  # noqa: E402
from models.content.conversation import AgentEvent as AgentEventRow  # noqa: E402
from models.membership import ProjectMember  # noqa: E402
from models.memory import (  # noqa: E402
    SCOPE_USER,
    SOURCE_USER,
    STATUS_ARCHIVED,
    STATUS_SUPERSEDED,
    ProjectMemory,
)
from models.project import Project  # noqa: E402
import routes.memory as memory_routes  # noqa: E402
import service.auth as auth_service  # noqa: E402
import service.memory_consolidation as consolidation  # noqa: E402
from service.membership import ROLE_OWNER  # noqa: E402
from service.memory import remember, search, seed_user_preferences, short_id  # noqa: E402
from service.memory_consolidation import (  # noqa: E402
    Consolidation,
    ExtractedEntry,
    MemoryClose,
    build_transcript,
)


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def owner(db):
    user = User(email="phase2@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Phase 2")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def service_db(engine, monkeypatch):
    """Point the consolidation service's own sessions at the test engine."""
    def _fake_db():
        yield Session(engine)

    monkeypatch.setattr(consolidation, "db_session", _fake_db)
    return engine


# ---------------------------------------------------------------------------
# Consolidation — the verdict is the model's, the writing is ours
# ---------------------------------------------------------------------------

def _conversation(db, project, *, turns: int = 8) -> AgentConversation:
    conv = AgentConversation(agent_type="audit_seo", project_id=project.id, mode="audit")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    for seq in range(1, turns + 1):
        db.add(AgentEventRow(
            conversation_id=conv.id, seq=seq,
            kind=EventKind.USER if seq % 2 else EventKind.ASSISTANT,
            data={"text": f"turn {seq}"},
        ))
    conv.last_seq = turns
    db.add(conv)
    db.commit()
    return conv


def test_apply_writes_entries_and_advances_the_watermark(db, project, service_db):
    conv = _conversation(db, project)
    verdict = Consolidation(entries=[
        ExtractedEntry(
            kind="incident", title="Clicks down 23% after the redirect",
            body="Why: redirect chain. How to apply: check indexing before a URL move.",
            entity_key="page:/pricing", attribute="clicks", observed_at="2026-08-14",
            seq_from=3, seq_to=6,
        ),
        ExtractedEntry(kind="decision", title="Ship the fix before the campaign"),
    ])

    result = consolidation._apply(
        verdict, project_id=project.id, conversation_id=conv.id,
        agent_type="audit_seo", last_seq=8,
    )

    assert result.written == 2
    rows = search(db, project_id=project.id)
    incident = next(r for r in rows if r.kind == "incident")
    # Traceable back to the turns it came from — the whole point of the seq refs.
    assert incident.source_refs[0]["conversation_id"] == str(conv.id)
    assert incident.source_refs[0]["seq"] == [3, 6]
    assert incident.observed_at.strftime("%Y-%m-%d") == "2026-08-14"
    db.refresh(conv)
    assert conv.meta["memory_through_seq"] == 8


def test_apply_rejects_kinds_the_model_invented(db, project, service_db):
    conv = _conversation(db, project)
    verdict = Consolidation(entries=[
        ExtractedEntry(kind="vibes", title="Feels good"),
        ExtractedEntry(kind="goal", title="Target CPA $45"),
    ])
    result = consolidation._apply(
        verdict, project_id=project.id, conversation_id=conv.id,
        agent_type="audit_seo", last_seq=8,
    )
    assert result.written == 1
    assert [r.kind for r in search(db, project_id=project.id)] == ["goal"]


def test_close_and_archive_are_scoped_to_the_project(db, owner, project, service_db):
    other = Project(user_id=owner.id, name="Other")
    db.add(other)
    db.commit()
    db.refresh(other)

    mine = remember(db, kind="incident", title="Open incident", project_id=project.id,
                    entity_key="page:/a", attribute="status", source_refs=[{"source": "t"}])
    noise = remember(db, kind="conclusion", title="Worthless guess", project_id=project.id,
                     source_refs=[{"source": "t"}])
    foreign = remember(db, kind="incident", title="Not yours", project_id=other.id,
                       entity_key="page:/b", attribute="status", source_refs=[{"source": "t"}])
    conv = _conversation(db, project)

    verdict = Consolidation(
        close=[
            MemoryClose(memory_id=short_id(mine.id), resolved_on="2026-08-21", reason="fixed"),
            # The model naming a row from another project must change nothing.
            MemoryClose(memory_id=short_id(foreign.id), resolved_on="2026-08-21"),
        ],
        archive=[short_id(noise.id)],
    )
    result = consolidation._apply(
        verdict, project_id=project.id, conversation_id=conv.id,
        agent_type="audit_seo", last_seq=8,
    )

    assert (result.closed, result.archived) == (1, 1)
    for row in (mine, noise, foreign):
        db.refresh(row)
    assert mine.valid_to is not None and mine.meta["closed_reason"] == "fixed"
    assert noise.status == STATUS_ARCHIVED
    assert foreign.valid_to is None


def test_consolidate_conversation_runs_once_per_watermark(db, project, service_db, monkeypatch):
    """The async path end to end, with the model's verdict stubbed.

    Second call over the same conversation must find nothing new to read —
    that is what stops a reconnecting client re-extracting the same session.
    """
    import asyncio

    conv = _conversation(db, project, turns=8)
    calls = []

    class _StubModel:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            return Consolidation(entries=[ExtractedEntry(kind="goal", title="Target CPA $45")])

    monkeypatch.setattr(consolidation, "_build_model", lambda: _StubModel())

    first = asyncio.run(consolidation.consolidate_conversation(conv.id))
    assert (first.written, first.through_seq) == (1, 8)
    # The digest and the untrusted-transcript guard both reach the model.
    assert "<untrusted_transcript>" in calls[0]
    assert "[1] user: turn 1" in calls[0]

    second = asyncio.run(consolidation.consolidate_conversation(conv.id))
    assert second.skipped == "too few new turns"
    assert len(calls) == 1
    assert len(search(db, project_id=project.id)) == 1


def test_consolidation_skips_short_sessions_and_paused_projects(db, project, service_db):
    import asyncio

    conv = _conversation(db, project, turns=2)
    assert "too few new turns" in asyncio.run(
        consolidation.consolidate_conversation(conv.id)
    ).skipped

    project.memory_paused = True
    db.add(project)
    db.commit()
    long_conv = _conversation(db, project, turns=10)
    assert "paused" in asyncio.run(
        consolidation.consolidate_conversation(long_conv.id)
    ).skipped


def test_transcript_numbers_turns_and_drops_noise(db, project):
    conv = _conversation(db, project, turns=3)
    rows = list(
        db.execute(
            select(AgentEventRow).where(AgentEventRow.conversation_id == conv.id)
        ).scalars()
    )
    rows.append(AgentEventRow(conversation_id=conv.id, seq=4, kind=EventKind.THINKING,
                              data={"text": "hmm"}))
    text = build_transcript(rows)
    assert "[1] user: turn 1" in text
    assert "[2] agent: turn 2" in text
    assert "hmm" not in text  # thinking is noise for extraction


# ---------------------------------------------------------------------------
# Pause — stop learning, without forgetting
# ---------------------------------------------------------------------------

def test_pause_blocks_agent_writes_but_not_reads_or_user_statements(db, project):
    kept = remember(db, kind="goal", title="Known before the pause", project_id=project.id,
                    source_refs=[{"source": "t"}])
    project.memory_paused = True
    db.add(project)
    db.commit()

    assert remember(db, kind="event", title="Agent noticed something",
                    project_id=project.id, source_refs=[{"source": "t"}]) is None
    # A person typing "remember this" is not the inference they paused.
    assert remember(db, kind="decision", title="I decided this", project_id=project.id,
                    source_type=SOURCE_USER, source_refs=[{"source": "user"}]) is not None
    # Reads are untouched: pausing is "stop learning", not "forget".
    assert kept.id in {r.id for r in search(db, project_id=project.id)}


def test_user_pause_is_independent_of_project_pause(db, owner, project):
    owner.memory_paused = True
    db.add(owner)
    db.commit()
    assert remember(db, scope=SCOPE_USER, kind="method", title="Inferred habit",
                    user_id=owner.id, source_refs=[{"source": "t"}]) is None
    assert remember(db, kind="event", title="Project fact", project_id=project.id,
                    source_refs=[{"source": "t"}]) is not None


# ---------------------------------------------------------------------------
# Declared preferences become user memory
# ---------------------------------------------------------------------------

def test_preferences_seed_and_supersede_on_change(db, owner):
    written = seed_user_preferences(
        db, owner.id,
        UserPreferences(role="Growth Manager", communication_style="executive",
                        report_depth="summary", primary_outcome="revenue"),
    )
    assert len(written) == 4
    assert all(r.scope == SCOPE_USER and r.source_type == SOURCE_USER for r in written)
    style = next(r for r in written if r.attribute == "communication_style")

    seed_user_preferences(db, owner.id, UserPreferences(communication_style="technical"))
    db.refresh(style)
    assert style.status == STATUS_SUPERSEDED
    assert "technical" in next(
        r.title for r in search(db, user_id=owner.id, scope=SCOPE_USER)
        if r.attribute == "communication_style"
    )


# ---------------------------------------------------------------------------
# Controls — pause, reset, export
# ---------------------------------------------------------------------------

@pytest.fixture
def client(db, owner):
    app = FastAPI()
    app.include_router(memory_routes.router, prefix="/api/user/projects")
    app.include_router(memory_routes.user_router, prefix="/api/user/memory")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: owner
    return TestClient(app)


def test_pause_route_toggles_the_project_switch(client, db, project):
    body = client.post(f"/api/user/projects/{project.id}/memory/pause", json={"paused": True})
    assert body.json()["memory_paused"] is True
    db.refresh(project)
    assert project.memory_paused is True


def test_timeline_reports_whether_the_project_is_paused(client, project):
    """The switch reads its state from the listing.

    Without it the control renders unchecked on every reload and tells the user
    memory is on while it is off.
    """
    assert client.get(f"/api/user/projects/{project.id}/memory").json()["memory_paused"] is False
    client.post(f"/api/user/projects/{project.id}/memory/pause", json={"paused": True})
    assert client.get(f"/api/user/projects/{project.id}/memory").json()["memory_paused"] is True


def test_an_unremembered_session_is_not_consolidated_when_it_closes(monkeypatch):
    """"Don't remember this session" has to hold at close time.

    Nothing else would catch it: the tools are unmounted and no digest is
    injected, but consolidation reads the stored transcript afterwards, which is
    exactly where the promise would break silently.
    """
    import routes.agents as agents_routes

    class _Session:
        conversation_id = uuid4()
        memory_off = True

    scheduled: list = []
    monkeypatch.setattr(agents_routes, "get_session", lambda _sid: _Session())
    monkeypatch.setattr(agents_routes, "close_session", lambda _sid: None)
    monkeypatch.setattr(agents_routes, "schedule_consolidation", scheduled.append)

    agents_routes._close_and_consolidate("sid")
    assert scheduled == [None]

    _Session.memory_off = False
    agents_routes._close_and_consolidate("sid")
    assert scheduled[-1] == _Session.conversation_id


def test_export_returns_everything_including_superseded(client, db, project):
    remember(db, kind="goal", title="Target CPA $60", project_id=project.id,
             entity_key="kpi:cpa", attribute="target", source_refs=[{"source": "t"}])
    remember(db, kind="goal", title="Target CPA $45", project_id=project.id,
             entity_key="kpi:cpa", attribute="target", source_refs=[{"source": "t"}])
    # "export" must not be swallowed by the /{memory_id} route declared near it.
    body = client.get(f"/api/user/projects/{project.id}/memory/export").json()
    assert len(body["memories"]) == 2
    assert body["exported_at"]


def test_reset_requires_confirmation(client, db, project):
    remember(db, kind="event", title="Something", project_id=project.id,
             source_refs=[{"source": "t"}])
    assert client.post(f"/api/user/projects/{project.id}/memory/reset").status_code == 422
    assert client.post(
        f"/api/user/projects/{project.id}/memory/reset?confirm=true"
    ).json()["deleted"] == 1
    assert db.execute(select(ProjectMemory)).scalars().all() == []


def test_user_scope_routes_are_private_to_the_caller(client, db, owner):
    created = client.post(
        "/api/user/memory",
        json={"kind": "method", "title": "Always compare to the same period last year"},
    )
    assert created.status_code == 201
    assert created.json()["scope"] == SCOPE_USER

    listed = client.get("/api/user/memory").json()
    assert [i["id"] for i in listed["items"]] == [created.json()["id"]]
    assert listed["memory_paused"] is False

    # A project-kind entry has no business in the user scope.
    assert client.post("/api/user/memory", json={"kind": "incident", "title": "x"}).status_code == 422

    stranger = User(email="stranger@example.com")
    db.add(stranger)
    db.commit()
    theirs = remember(db, scope=SCOPE_USER, kind="method", title="Theirs",
                      user_id=stranger.id, source_refs=[{"source": "t"}])
    assert client.delete(f"/api/user/memory/{theirs.id}").status_code == 404


def test_user_reset_clears_only_the_callers_memory(client, db, owner):
    stranger = User(email="other@example.com")
    db.add(stranger)
    db.commit()
    remember(db, scope=SCOPE_USER, kind="method", title="Mine", user_id=owner.id,
             source_refs=[{"source": "t"}])
    remember(db, scope=SCOPE_USER, kind="method", title="Theirs", user_id=stranger.id,
             source_refs=[{"source": "t"}])
    assert client.post("/api/user/memory/reset?confirm=true").json()["deleted"] == 1
    assert [r.title for r in db.execute(select(ProjectMemory)).scalars()] == ["Theirs"]


def test_artifact_summary_backfills_the_memory_entry_body(db, project, owner):
    from models.artifact import Artifact
    from service.memory import backfill_artifact_summary, record_artifact_memory

    artifact = Artifact(group_id=uuid4(), version=1, project_id=project.id,
                        user_id=owner.id, kind="report", title="SEO audit", slug="a")
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    entry = record_artifact_memory(db, artifact)
    assert entry.body == ""  # the summary lands seconds later, from a background task

    backfill_artifact_summary(db, artifact, "Score 72. Two FAILs on indexation.")
    db.refresh(entry)
    assert entry.body.startswith("Score 72.")
