"""Unit tests for audit-session conversation persistence (Phase 2 plumbing)."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import make_sqlite_engine
from sqlmodel import Session, select

from agents.core.session import close_session
from models.auth import User
from models.content import AgentConversation
from models.membership import ProjectMember
from models.project import Project
import routes.agents as agents_routes
from service.membership import ROLE_OWNER


@pytest.fixture
def engine():
    engine = make_sqlite_engine()
    return engine


@pytest.fixture
def project(engine):
    from types import SimpleNamespace

    with Session(engine) as db:
        owner = User(email="audit-conv@example.com")
        db.add(owner)
        db.commit()
        db.refresh(owner)
        row = Project(user_id=owner.id, name="Conv Test")
        db.add(row)
        db.commit()
        db.refresh(row)
        db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
        db.commit()
        # Detach-safe handle — the ORM row dies with this session.
        return SimpleNamespace(id=row.id)


@pytest.fixture
def patched_db(engine, monkeypatch):
    def _fake_db():
        yield Session(engine)

    monkeypatch.setattr(agents_routes, "db_session", _fake_db)
    return engine


def _create(body):
    sid = str(uuid.uuid4())
    session = agents_routes._create_session_for("audit_seo", sid, body)
    return sid, session


def test_project_scoped_audit_creates_conversation(patched_db, project, engine):
    sid, session = _create({
        "url": "https://example.com",
        "project_id": str(project.id),
        "report_mode": "template",
    })
    try:
        assert session.conversation_id is not None
        assert session.recorder is not None
        assert getattr(session, "resume", False) is False
        with Session(engine) as db:
            conv = db.exec(select(AgentConversation)).one()
            assert conv.agent_type == "audit_seo"
            assert conv.project_id == project.id
            assert conv.mode == "template"
            assert conv.title == "SEO audit — https://example.com"
            assert conv.meta["url"] == "https://example.com"
    finally:
        close_session(sid)


def test_resume_reuses_conversation(patched_db, project, engine):
    sid1, s1 = _create({"url": "https://example.com", "project_id": str(project.id)})
    conv_id = s1.conversation_id
    close_session(sid1)
    # Simulate prior history so resume reports is_resume=True.
    from agents.content.persistence import append_event

    with Session(engine) as db:
        append_event(db, conv_id, "user", {"content": "hello"})

    sid2, s2 = _create({
        "url": "https://example.com",
        "project_id": str(project.id),
        "conversation_id": str(conv_id),
        "resume": True,
    })
    try:
        assert s2.conversation_id == conv_id
        assert s2.resume is True
    finally:
        close_session(sid2)


def test_lead_magnet_and_anonymous_stay_ephemeral(patched_db, project):
    sid1, s1 = _create({
        "url": "https://example.com",
        "project_id": str(project.id),
        "lead_magnet": True,
    })
    sid2, s2 = _create({"url": "https://example.com"})
    sid3, s3 = _create({"url": "https://example.com", "project_id": "local-abc123"})
    try:
        for s in (s1, s2, s3):
            assert getattr(s, "conversation_id", None) is None
            assert getattr(s, "recorder", None) is None
    finally:
        for sid in (sid1, sid2, sid3):
            close_session(sid)
