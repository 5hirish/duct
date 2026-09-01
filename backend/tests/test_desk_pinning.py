"""Pinning — the desk's one write, on both of the things it lists.

Pinning is display order and nothing else: it must not change what a listing
returns, which version is head, or who can see a row. The tests that matter
here are therefore mostly about what pinning *doesn't* do.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from db.session import get_session as get_session_dep
from models.artifact import Artifact
from models.auth import User
from models.content.conversation import AgentConversation
from models.membership import ProjectMember
from models.project import Project
import routes.artifacts as artifact_routes
import service.auth as auth_service
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine


@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


@pytest.fixture
def owner(db):
    user = User(email="desk-owner@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def stranger(db):
    user = User(email="desk-stranger@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Desk")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def brief(db, project, owner):
    """Three versions of one brief — the shape a pin has to cope with."""
    group = uuid4()
    rows = [
        Artifact(
            group_id=group,
            version=v,
            project_id=project.id,
            user_id=owner.id,
            agent_type="insights",
            kind="brief",
            content_type="text/markdown",
            title=f"Growth brief v{v}",
        )
        for v in (1, 2, 3)
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def client(db, user):
    app = FastAPI()
    app.include_router(artifact_routes.router, prefix="/api/user/artifacts")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app)


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def test_pinning_applies_to_every_version_of_the_group(db, brief, owner):
    """The library lists the newest version per group. A pin stored on one row
    would vanish the next time the agent wrote one — so it goes on all of them."""
    res = client(db, owner).patch(f"/api/user/artifacts/{brief[0].id}", json={"pinned": True})
    assert res.status_code == 200
    assert res.json()["pinned"] is True

    for row in brief:
        db.refresh(row)
    assert [row.pinned for row in brief] == [True, True, True]


def test_unpinning_clears_the_whole_group_too(db, brief, owner):
    c = client(db, owner)
    c.patch(f"/api/user/artifacts/{brief[2].id}", json={"pinned": True})
    c.patch(f"/api/user/artifacts/{brief[0].id}", json={"pinned": False})
    for row in brief:
        db.refresh(row)
    assert not any(row.pinned for row in brief)


def test_a_pin_does_not_change_which_version_is_head(db, brief, project, owner):
    c = client(db, owner)
    c.patch(f"/api/user/artifacts/{brief[0].id}", json={"pinned": True})
    listed = c.get(f"/api/user/artifacts?project_id={project.id}").json()
    assert len(listed) == 1, "still one row per group"
    assert listed[0]["version"] == 3
    assert listed[0]["pinned"] is True
    assert listed[0]["version_count"] == 3


def test_the_listing_carries_the_flag_so_the_desk_can_sort(db, brief, project, owner):
    listed = client(db, owner).get(f"/api/user/artifacts?project_id={project.id}").json()
    assert listed[0]["pinned"] is False


def test_a_non_member_cannot_pin_and_is_not_told_it_exists(db, brief, stranger):
    res = client(db, stranger).patch(
        f"/api/user/artifacts/{brief[0].id}", json={"pinned": True}
    )
    assert res.status_code == 404
    db.refresh(brief[0])
    assert brief[0].pinned is False


def test_pinned_is_the_only_field_the_patch_accepts(db, brief, owner):
    """Content is immutable — a change is a new version, which is what restore
    is for. A patch that could rewrite a stored title would break that."""
    res = client(db, owner).patch(
        f"/api/user/artifacts/{brief[0].id}", json={"title": "rewritten"}
    )
    assert res.status_code == 422
    db.refresh(brief[0])
    assert brief[0].title == "Growth brief v1"


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def test_a_conversation_starts_unpinned(db, project):
    conv = AgentConversation(agent_type="insights", project_id=project.id, title="Funnel")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    assert conv.pinned is False


def test_the_conversation_summary_exposes_the_flag(db, project):
    """The desk sorts on this field, so it has to survive serialisation."""
    from routes.agents import _conversation_summary

    conv = AgentConversation(
        agent_type="insights", project_id=project.id, title="Funnel", pinned=True
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    assert _conversation_summary(conv)["pinned"] is True
