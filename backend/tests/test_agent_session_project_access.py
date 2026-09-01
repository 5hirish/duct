"""Who may start an agent against a project.

`POST /api/agents/{type}/sessions` takes `project_id` in the request body, and
the body is not evidence. Everything project-scoped hangs off that id: the
content agent's MCP server (brand context, plans, posts, assets — and
PublishPost, which posts to the project's linked social accounts), the audit and
insights artifact stores, project memory. It was checked in two of the three
active agents and not in the third.

The gate lives in `_scope_body_to_authorized_project`, which is called before
anything reads the body. These tests pin its two different answers:

  * tiktok_studio has no unscoped mode — the session is built from the project —
    so an unauthorized id is a 404, the same reply a made-up one gets.
  * an audit or a brief drops the scope and runs anyway, which is what they
    already did for a local-only (non-UUID) project id. Rejecting would break a
    signed-in user whose new project has not finished syncing yet.

Written from the stranger's side: that a member gets their own project through
is table stakes; the assertions worth having are the ones about someone who
should get nothing.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session

from db.session import get_session as get_session_dep
from models.auth import User
from models.membership import ProjectMember
from models.project import Project
import routes.agents as agent_routes
import service.auth as auth_service
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

TIKTOK = "tiktok_studio"
AUDIT = "audit_seo"


@pytest.fixture
def engine(monkeypatch):
    """In-memory DB wired into the route module's direct `db_session()` calls.

    The gate opens its own session rather than taking one as a FastAPI
    dependency, so `dependency_overrides` cannot reach it — the module
    attribute is the seam.
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
    return _user(db, "session-owner@example.com")


@pytest.fixture
def stranger(db):
    """Signed in, holding the same public API key the browser bundle ships."""
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


def _body(project_id, **extra):
    """A session-create body carrying project scope and the resume controls."""
    return {
        "project_id": str(project_id),
        "conversation_id": str(uuid4()),
        "resume": True,
        "prompt": "what changed this week",
        **extra,
    }


# ---------------------------------------------------------------------------
# The member is untouched
# ---------------------------------------------------------------------------

def test_a_member_keeps_their_project_scope(db, project, owner):
    body = _body(project.id)
    before = dict(body)
    agent_routes._scope_body_to_authorized_project(AUDIT, body, owner)
    assert body == before


def test_a_member_may_start_the_content_agent(db, project, owner):
    body = _body(project.id, mode="plan_month")
    agent_routes._scope_body_to_authorized_project(TIKTOK, body, owner)
    assert body["project_id"] == str(project.id)


# ---------------------------------------------------------------------------
# The stranger: 404 where scope is mandatory, dropped where it is optional
# ---------------------------------------------------------------------------

def test_a_stranger_cannot_start_the_content_agent(db, project, stranger):
    with pytest.raises(HTTPException) as exc:
        agent_routes._scope_body_to_authorized_project(
            TIKTOK, _body(project.id, mode="plan_month"), stranger
        )
    assert exc.value.status_code == 404


def test_an_anonymous_caller_cannot_start_the_content_agent(db, project):
    """The API key alone got here before. It proves "this is the Duct app"."""
    with pytest.raises(HTTPException) as exc:
        agent_routes._scope_body_to_authorized_project(
            TIKTOK, _body(project.id, mode="plan_month"), None
        )
    assert exc.value.status_code == 404


def test_a_real_project_answers_like_a_made_up_one(db, project, stranger):
    """404 both ways, so the reply is not an oracle for which ids are real."""

    def _refusal(project_id):
        with pytest.raises(HTTPException) as exc:
            agent_routes._scope_body_to_authorized_project(TIKTOK, _body(project_id), stranger)
        return exc.value.status_code, exc.value.detail

    assert _refusal(project.id) == _refusal(uuid4()) == (404, "Project not found")


def test_a_strangers_audit_runs_unscoped_rather_than_failing(db, project, stranger):
    body = _body(project.id)
    agent_routes._scope_body_to_authorized_project(AUDIT, body, stranger)
    assert "project_id" not in body
    assert body["prompt"] == "what changed this week"  # the run itself survives


def test_the_resume_controls_go_with_the_scope(db, project, stranger):
    """A conversation_id is resolved without a project check of its own, so
    leaving it behind would still address someone else's transcript."""
    body = _body(project.id, artifact_type="post", artifact_id=str(uuid4()), start_fresh=True)
    agent_routes._scope_body_to_authorized_project(AUDIT, body, stranger)
    for key in ("project_id", "conversation_id", "resume", "start_fresh",
                "artifact_type", "artifact_id"):
        assert key not in body


def test_an_anonymous_audit_runs_unscoped(db, project):
    """The lead-magnet teaser is anonymous by design and owns no project."""
    body = _body(project.id)
    agent_routes._scope_body_to_authorized_project(AUDIT, body, None)
    assert "project_id" not in body


# ---------------------------------------------------------------------------
# What the gate deliberately leaves alone
# ---------------------------------------------------------------------------

def test_a_local_only_project_id_is_left_alone(db, owner):
    """Desktop projects that never synced aren't UUIDs; downstream already
    reads that as "run unscoped" and must keep doing so."""
    body = {"project_id": "local-draft-7", "prompt": "hi"}
    agent_routes._scope_body_to_authorized_project(AUDIT, body, owner)
    assert body["project_id"] == "local-draft-7"


def test_a_missing_project_id_is_left_alone(db, owner):
    body = {"prompt": "hi"}
    agent_routes._scope_body_to_authorized_project(AUDIT, body, owner)
    assert body == {"prompt": "hi"}


def test_a_missing_project_id_still_reaches_tiktoks_own_422(db, owner):
    """The gate must not turn "you forgot project_id" into "not found"."""
    body = {"mode": "plan_month"}
    agent_routes._scope_body_to_authorized_project(TIKTOK, body, owner)  # no raise
    with pytest.raises(HTTPException) as exc:
        agent_routes._create_session_for(TIKTOK, str(uuid4()), body)
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# The wiring: the gate runs before the body is used
# ---------------------------------------------------------------------------

def test_the_route_refuses_before_building_a_session(db, project, stranger, monkeypatch):
    built: list = []
    monkeypatch.setattr(
        agent_routes, "_create_session_for",
        lambda *a, **k: built.append(a) or pytest.fail("session built for a non-member"),
    )

    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api/agents")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user_optional] = lambda: stranger

    res = TestClient(app, raise_server_exceptions=False).post(
        f"/api/agents/{TIKTOK}/sessions", json=_body(project.id, mode="plan_month")
    )
    assert res.status_code == 404
    assert built == []
