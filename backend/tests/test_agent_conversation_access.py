"""Who may read and change an agent conversation.

The four conversation endpoints were mounted behind `validate_api_key` and
nothing else. That key ships to the browser as NEXT_PUBLIC_DUCT_API_KEY, so it
proves "this is the Duct app" and never "this is that conversation's owner" —
which made every transcript in the database readable by anyone holding a bundle
they could download. These tests pin the gate that closed it.

They are written from the stranger's side on purpose: the interesting assertion
is not that a member gets their data, it is that a non-member gets a 404 and
learns nothing from it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from db.session import get_session as get_session_dep
from models.auth import User
from models.content import AgentConversation, AgentEvent
from models.membership import ProjectMember
from models.project import Project
import routes.agents as agent_routes
import service.auth as auth_service
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

AGENT = "insights"
SECRET = "Q3 churn is concentrated in the self-serve tier."


@pytest.fixture
def engine(monkeypatch):
    """In-memory DB, wired into the route module's direct `db_session()` calls.

    The endpoints open their own session rather than taking one as a FastAPI
    dependency, so `dependency_overrides` cannot reach them — the module
    attribute is the seam. A fresh Session per call is fine: StaticPool means
    they all share the one in-memory connection.
    """
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
    return _user(db, "conv-owner@example.com")


@pytest.fixture
def stranger(db):
    """Signed in, with a perfectly good API key — and no business here."""
    return _user(db, "conv-stranger@example.com")


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
def conversation(db, project):
    conv = AgentConversation(
        agent_type=AGENT, project_id=project.id, title="Churn review", last_seq=1
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.add(AgentEvent(conversation_id=conv.id, seq=1, kind="assistant", data={"text": SECRET}))
    db.commit()
    return conv


def client(db, user=None):
    """A client for `user`, or an unauthenticated one when user is None."""
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api/agents")
    app.dependency_overrides[get_session_dep] = lambda: db
    if user is not None:
        app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _url(conv_id=None):
    base = f"/api/agents/{AGENT}/conversations"
    return base if conv_id is None else f"{base}/{conv_id}"


# ---------------------------------------------------------------------------
# The member still gets everything they had
# ---------------------------------------------------------------------------

def test_a_member_lists_their_own_conversations(db, conversation, project, owner):
    rows = client(db, owner).get(f"{_url()}?project_id={project.id}").json()
    assert [r["id"] for r in rows] == [str(conversation.id)]


def test_a_member_reads_the_transcript(db, conversation, owner):
    body = client(db, owner).get(_url(conversation.id)).json()
    assert body["conversation"]["title"] == "Churn review"
    assert [e["data"]["text"] for e in body["events"]] == [SECRET]


def test_an_unfiltered_list_still_returns_the_callers_own(db, conversation, owner):
    """Dropping project_id used to mean "every tenant". It now means "mine"."""
    rows = client(db, owner).get(_url()).json()
    assert [r["id"] for r in rows] == [str(conversation.id)]


# ---------------------------------------------------------------------------
# The stranger gets nothing, and learns nothing
# ---------------------------------------------------------------------------

def test_a_stranger_cannot_read_the_transcript(db, conversation, stranger):
    res = client(db, stranger).get(_url(conversation.id))
    assert res.status_code == 404
    assert SECRET not in res.text


def test_a_stranger_naming_the_project_is_told_it_does_not_exist(db, conversation, project, stranger):
    """404, not 403 — the same answer a made-up project id gets, so the reply
    is not an oracle for which ids are real."""
    res = client(db, stranger).get(f"{_url()}?project_id={project.id}")
    assert res.status_code == 404
    assert res.json() == client(db, stranger).get(f"{_url()}?project_id={uuid4()}").json()


def test_a_stranger_listing_everything_sees_only_their_own(db, conversation, stranger):
    """The widest hole of the four: this enumerated the ids that the read
    endpoint would then hand over in full."""
    assert client(db, stranger).get(_url()).json() == []


def test_a_stranger_cannot_pin_or_rename(db, conversation, stranger):
    res = client(db, stranger).patch(_url(conversation.id), json={"pinned": True, "title": "hi"})
    assert res.status_code == 404
    db.refresh(conversation)
    assert conversation.pinned is False
    assert conversation.title == "Churn review"


def test_a_stranger_cannot_archive(db, conversation, stranger):
    res = client(db, stranger).post(f"{_url(conversation.id)}/archive")
    assert res.status_code == 404
    db.refresh(conversation)
    assert conversation.status == "active"


# ---------------------------------------------------------------------------
# Signed out, and other ways in
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path_suffix",
    [("get", ""), ("get", "/{id}"), ("patch", "/{id}"), ("post", "/{id}/archive")],
)
def test_every_conversation_endpoint_requires_a_signed_in_caller(db, conversation, method, path_suffix):
    """The API key alone is not identity. All four say so."""
    path = _url() + path_suffix.format(id=conversation.id)
    res = getattr(client(db), method)(path, **({"json": {}} if method == "patch" else {}))
    assert res.status_code == 401


def test_the_wrong_agent_type_is_not_found(db, conversation, owner):
    """Conversation ids are unique, but the route is typed — asking the audit
    agent for an insights thread must not resolve."""
    res = client(db, owner).get(f"/api/agents/audit_seo/conversations/{conversation.id}")
    assert res.status_code == 404


def test_a_malformed_conversation_id_is_a_404_not_a_crash(db, owner):
    assert client(db, owner).get(_url("not-a-uuid")).status_code == 404


def test_a_malformed_project_id_is_rejected(db, owner):
    assert client(db, owner).get(f"{_url()}?project_id=not-a-uuid").status_code == 422
