"""Who may read and change a project's content.

The content router carried 44 endpoints and not one auth dependency. Behind it
sat every plan, post, format, avatar and uploaded asset in the database, each
reachable with nothing but `NEXT_PUBLIC_DUCT_API_KEY` — a value compiled into
the browser bundle. `GET /content/posts?project_id=…` read another tenant's
board; `DELETE /content/posts/{id}` emptied it; `POST .../publish` pushed their
drafts to a social account.

Two things are being pinned here. Per-endpoint, that a stranger gets 404 and
nothing else. Structurally, that *every* route on the router demands a signed-in
caller — the last test is the one that will still be doing work in a year, when
endpoint 45 is written by someone who never read this file.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from db.session import get_session as get_session_dep
from models.auth import User
from models.content import (
    ContentAsset,
    ContentAvatar,
    ContentFormat,
    ContentPlan,
    ContentPost,
)
from models.membership import ProjectMember
from models.project import Project
import routes.content as content_routes
import service.auth as auth_service
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine


@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


def _user(db, email):
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def owner(db):
    return _user(db, "content-owner@example.com")


@pytest.fixture
def stranger(db):
    """Signed in, holding a valid API key, and entitled to none of this."""
    return _user(db, "content-stranger@example.com")


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Owner's brand")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def content(db, project):
    """One row of every project-scoped kind the router exposes."""
    rows = {
        "plan": ContentPlan(project_id=project.id, name="September"),
        "post": ContentPost(
            project_id=project.id,
            post_dir_slug="launch-day",
            caption="Ours",
            # The board hides pending drafts, so a pending row would make
            # the listing test pass for the wrong reason.
            status="draft",
        ),
        "format": ContentFormat(project_id=project.id, slug="carousel", name="Carousel"),
        "avatar": ContentAvatar(project_id=project.id, name="Host"),
        "asset": ContentAsset(
            project_id=project.id, asset_type="logo", url="/uploads/logo.png"
        ),
    }
    db.add_all(rows.values())
    db.commit()
    for row in rows.values():
        db.refresh(row)
    return rows


def client(db, user=None):
    """A client for `user`, or an unauthenticated one when user is None."""
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    if user is not None:
        app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# The member's work still works
# ---------------------------------------------------------------------------

def test_a_member_sees_their_board(db, content, project, owner):
    rows = client(db, owner).get(f"/api/content/posts?project_id={project.id}").json()
    assert [r["caption"] for r in rows] == ["Ours"]


def test_a_member_opens_their_post(db, content, owner):
    body = client(db, owner).get(f"/api/content/posts/{content['post'].id}").json()
    assert body["caption"] == "Ours"


def test_a_member_edits_their_post(db, content, owner):
    res = client(db, owner).patch(
        f"/api/content/posts/{content['post'].id}", json={"caption": "Edited"}
    )
    assert res.status_code == 200
    db.refresh(content["post"])
    assert content["post"].caption == "Edited"


# ---------------------------------------------------------------------------
# The stranger reads nothing, changes nothing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kind, path",
    [
        ("plan", "/api/content/plans/{id}"),
        ("post", "/api/content/posts/{id}"),
    ],
)
def test_a_stranger_cannot_read_a_row(db, content, stranger, kind, path):
    res = client(db, stranger).get(path.format(id=content[kind].id))
    assert res.status_code == 404


@pytest.mark.parametrize(
    "kind, path",
    [
        ("plan", "/api/content/plans/{id}"),
        ("post", "/api/content/posts/{id}"),
        ("format", "/api/content/formats/{id}"),
        ("avatar", "/api/content/avatars/{id}"),
        ("asset", "/api/content/assets/{id}"),
    ],
)
def test_a_stranger_cannot_delete_a_row(db, content, stranger, kind, path):
    """The destructive half. A 404 here has to mean the row survived."""
    res = client(db, stranger).delete(path.format(id=content[kind].id))
    assert res.status_code == 404
    db.refresh(content[kind])  # raises if it was deleted
    assert content[kind].id is not None


def test_a_stranger_cannot_edit_a_post(db, content, stranger):
    res = client(db, stranger).patch(
        f"/api/content/posts/{content['post'].id}", json={"caption": "Defaced"}
    )
    assert res.status_code == 404
    db.refresh(content["post"])
    assert content["post"].caption == "Ours"


def test_a_stranger_cannot_publish_someone_elses_post(db, content, stranger):
    """The worst of the writes: this one leaves the building."""
    res = client(db, stranger).post(
        f"/api/content/posts/{content['post'].id}/publish",
        json={"social_account_ids": [1]},
    )
    assert res.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/content/posts?project_id={id}",
        "/api/content/plans?project_id={id}",
        "/api/content/formats?project_id={id}",
        "/api/content/avatars?project_id={id}",
        "/api/content/assets?project_id={id}",
        "/api/content/brand?project_id={id}",
        "/api/content/linked-accounts?project_id={id}",
    ],
)
def test_a_stranger_naming_the_project_is_told_it_does_not_exist(db, content, project, stranger, path):
    """404, not 403 and not an empty list — the same answer a made-up id gets,
    so a listing cannot be used to discover which projects are real."""
    c = client(db, stranger)
    assert c.get(path.format(id=project.id)).status_code == 404
    assert c.get(path.format(id=uuid4())).status_code == 404


def test_a_stranger_cannot_plant_a_post_in_another_project(db, project, stranger):
    """Creates take the project from the body, which is the caller talking."""
    res = client(db, stranger).post(
        "/api/content/posts",
        json={"project_id": str(project.id), "post_dir_slug": "smuggled"},
    )
    assert res.status_code == 404
    assert db.get(ContentPost, res.json().get("id")) is None if res.json().get("id") else True


def test_the_row_decides_access_not_the_request(db, content, stranger, owner):
    """A row endpoint reads the project off the row. Naming your own project in
    the query string must not launder a reach into someone else's."""
    res = client(db, stranger).get(
        f"/api/content/posts/{content['post'].id}?project_id={uuid4()}"
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Signed out
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/content/posts?project_id={pid}"),
        ("get", "/api/content/plans?project_id={pid}"),
        ("get", "/api/content/brand?project_id={pid}"),
        ("get", "/api/content/analytics?project_id={pid}"),
        ("get", "/api/content/styles"),
        ("delete", "/api/content/posts/{post}"),
        ("post", "/api/content/posts/{post}/mark-posted"),
    ],
)
def test_the_api_key_alone_gets_nothing(db, content, project, method, path):
    url = path.format(pid=project.id, post=content["post"].id)
    assert getattr(client(db), method)(url).status_code == 401


def test_every_route_on_the_router_demands_a_signed_in_caller():
    """The structural one.

    Authentication is declared once on the router rather than 44 times, so that
    a new endpoint cannot be added without it. This asserts that property
    directly instead of trusting the list above to stay complete — if someone
    later builds their own APIRouter here, or drops the dependency, this fails
    while every other test still passes.
    """
    def dependency_names(dependant):
        for dep in dependant.dependencies:
            if dep.call is not None:
                yield getattr(dep.call, "__name__", "")
            yield from dependency_names(dep)

    routes = [r for r in content_routes.router.routes if hasattr(r, "dependant")]
    assert len(routes) >= 40, "expected the full content surface"
    missing = [
        f"{sorted(r.methods)} {r.path}"
        for r in routes
        if "get_current_user" not in set(dependency_names(r.dependant))
    ]
    assert missing == [], f"routes reachable without a user: {missing}"
