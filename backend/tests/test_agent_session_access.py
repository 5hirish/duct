"""Who may drive a live agent session.

A session id is a uuid4, and for a long time that was the whole of the
protection: anyone holding one could stream another user's agent, send messages
into it, read its state, or close it mid-run. Unguessable is not a permission —
ids reach logs, shared URLs and Sentry breadcrumbs.

Ownership rather than membership, because a session is in-memory and not always
project-scoped. The three cases that exist are covered here: a session stamped
with its creator (the normal path), a legacy `/api/content/*/stream` session
that only knows its project, and an anonymous lead-magnet audit that belongs to
nobody and must keep working signed out.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from agents.audit.v3.runner import close_session, create_audit_session
from agents.core.session import get_session
from models.auth import User
from models.membership import ProjectMember
from models.project import Project
import routes.agents as agent_routes
import service.auth as auth_service
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

AGENT = "audit_seo"


@pytest.fixture
def engine(monkeypatch):
    eng = make_sqlite_engine()

    def _fake_db():
        yield Session(eng)

    monkeypatch.setattr(agent_routes, "db_session", _fake_db)
    return eng


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


def _user(db, email):
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def owner(db):
    return _user(db, "session-owner@example.com")


@pytest.fixture
def stranger(db):
    return _user(db, "session-stranger@example.com")


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Owner's project")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def session():
    """A live session, torn down however the test leaves it."""
    made = []

    def _make(*, user_id=None, project_id=None):
        sid = str(uuid.uuid4())
        s = create_audit_session(sid, AGENT)
        s.user_id = user_id
        if project_id is not None:
            s.project_id = project_id
        made.append(sid)
        return sid

    yield _make
    for sid in made:
        close_session(sid)


def client(db, user=None):
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api/agents")
    if user is not None:
        app.dependency_overrides[auth_service.get_current_user_optional] = lambda: user
    else:
        app.dependency_overrides[auth_service.get_current_user_optional] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _base(sid):
    return f"/api/agents/{AGENT}/sessions/{sid}"


# ---------------------------------------------------------------------------
# A session stamped with its creator
# ---------------------------------------------------------------------------

def test_the_creator_can_read_and_drive_their_session(db, session, owner):
    sid = session(user_id=owner.id)
    c = client(db, owner)
    assert c.get(_base(sid)).status_code == 200
    assert c.post(f"{_base(sid)}/messages", json={"type": "chat", "content": "hi"}).status_code == 200


@pytest.mark.parametrize("method, suffix, body", [
    ("get", "", None),
    ("post", "/messages", {"type": "chat", "content": "steal"}),
])
def test_a_different_user_is_told_it_does_not_exist(db, session, owner, stranger, method, suffix, body):
    sid = session(user_id=owner.id)
    kwargs = {"json": body} if body is not None else {}
    res = getattr(client(db, stranger), method)(_base(sid) + suffix, **kwargs)
    assert res.status_code == 404


def test_a_different_user_cannot_open_the_stream(db, session, owner, stranger):
    """Read the status without consuming the body.

    A plain `.get()` here would block forever the moment this regresses: the
    stream stays open for the session lifetime, so a stranger who is let in
    hangs the test rather than failing it, and CI reports a timeout instead of
    the security hole. Ask for the headers and stop.
    """
    sid = session(user_id=owner.id)
    with client(db, stranger).stream("GET", f"{_base(sid)}/stream") as res:
        assert res.status_code == 404


def test_a_signed_out_caller_cannot_drive_an_owned_session(db, session, owner):
    """The API key on its own used to be enough for all of this."""
    sid = session(user_id=owner.id)
    assert client(db).get(_base(sid)).status_code == 404


def test_a_stranger_cannot_close_someone_elses_run(db, session, owner, stranger):
    """Close answers ok either way — but only actually closes your own."""
    sid = session(user_id=owner.id)
    assert client(db, stranger).delete(_base(sid)).status_code == 200
    assert get_session(sid) is not None, "the owner's run was killed by a stranger"

    assert client(db, owner).delete(_base(sid)).status_code == 200
    assert get_session(sid) is None


def test_closing_an_unknown_session_is_still_ok(db, owner):
    """Teardown is idempotent; a client should not have to win the race."""
    res = client(db, owner).delete(_base(uuid.uuid4()))
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# The legacy content sessions, which only know their project
# ---------------------------------------------------------------------------

def test_a_project_scoped_session_falls_back_to_membership(db, session, project, owner, stranger):
    """`/api/content/*/stream` builds sessions directly and never sets user_id,
    so the project is the only handle there is."""
    sid = session(user_id=None, project_id=project.id)
    assert client(db, owner).get(_base(sid)).status_code == 200
    assert client(db, stranger).get(_base(sid)).status_code == 404
    assert client(db).get(_base(sid)).status_code == 404


# ---------------------------------------------------------------------------
# The anonymous one, which has to keep working
# ---------------------------------------------------------------------------

def test_the_lead_magnet_audit_still_runs_signed_out(db, session):
    """No user and no project: the teaser audit on the marketing site. It holds
    nothing belonging to anyone, and there is no identity to compare against."""
    sid = session(user_id=None, project_id=None)
    assert client(db).get(_base(sid)).status_code == 200


def test_the_wrong_agent_type_is_not_found(db, session, owner):
    sid = session(user_id=owner.id)
    res = client(db, owner).get(f"/api/agents/insights/sessions/{sid}")
    assert res.status_code == 404
