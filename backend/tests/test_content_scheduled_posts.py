"""A post scheduled through PostBridge lives in two places until it goes out.

Editing it, unscheduling it or deleting it here used to change only the row,
so PostBridge's queue published the words the person had already changed, or
a post they had already deleted. These tests run the real routes, the agent's
rewrite and the real PostBridge client against a faked queue, and assert what
reached it.
"""

from __future__ import annotations

import asyncio
import json
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import agents.content.tools as content_tools
import routes.content as content_routes
import service.auth as auth_service
import service.post_bridge as post_bridge
from agents.content.publishing import PUBLISHED_VIA_DUCT
from agents.content.schema import ContentStatus, TEXT_POST_TYPE
from agents.content.v1.runner import make_session
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentPost
from models.membership import ProjectMember
from models.project import Project
from service.membership import ROLE_OWNER
from service.post_bridge import PostBridgeClient
from tests.conftest import make_sqlite_engine

WHEN = "2026-10-01T09:30:00Z"
PB_ID = "pb_post_1"


class PostBridgeQueue:
    """PostBridge's posts endpoints over a dict, recording every request."""

    def __init__(self) -> None:
        self.posts: dict[str, dict] = {}
        self.requests: list[tuple[str, str, dict | None]] = []
        self.create_status = "scheduled"
        self.down = False
        # The accounts a publish checks first: 101 is the X account every
        # test posts to.
        self.accounts: list[dict] = [{"id": 101, "platform": "twitter", "username": "duct"}]

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.read()) if req.content else None
        self.requests.append((req.method, req.url.path, body))
        if self.down:
            return httpx.Response(503, json={"message": "maintenance"})
        if req.method == "GET" and req.url.path == "/v1/social-accounts":
            return httpx.Response(200, json={"data": self.accounts})
        if req.method == "POST" and req.url.path == "/v1/posts":
            post = {"id": PB_ID, "caption": body["caption"], "status": self.create_status,
                    "scheduled_at": body.get("scheduled_at"), "social_accounts": body["social_accounts"]}
            if self.create_status == "failed":
                post["warnings"] = ["The X account needs reconnecting."]
            self.posts[PB_ID] = post
            return httpx.Response(200, json=post)
        post_id = req.url.path.removeprefix("/v1/posts/")
        post = self.posts.get(post_id)
        if post is None:
            return httpx.Response(404, json={"message": "Post not found"})
        if req.method == "GET":
            return httpx.Response(200, json=post)
        if req.method == "PATCH":
            post.update(body)
            return httpx.Response(200, json=post)
        if req.method == "DELETE":
            if post["status"] not in ("scheduled", "draft"):
                return httpx.Response(400, json={"message": "Can only delete scheduled or draft posts"})
            del self.posts[post_id]
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected PostBridge call: {req.method} {req.url.path}")

    def client(self, *_args) -> PostBridgeClient:
        return PostBridgeClient("sk-fake", client=httpx.AsyncClient(transport=httpx.MockTransport(self)))

    def calls(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.requests]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    return make_sqlite_engine()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def owner(db):
    row = User(email="writer@example.com")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Kestrel Studio", slug="kestrel")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def queue(monkeypatch) -> PostBridgeQueue:
    q = PostBridgeQueue()
    monkeypatch.setattr(post_bridge, "client_for_user", q.client)
    return q


def _queued(db, project, queue, *, caption="Shipped the eval gate.", replies=("Source: our CI logs.",)) -> ContentPost:
    """A tweet already on PostBridge's queue, as a publish would leave it —
    minus the stored time, like every post the agent scheduled before #272."""
    row = ContentPost(
        project_id=project.id, post_dir_slug="2026-09-28-001", post_type=TEXT_POST_TYPE,
        caption=caption, replies=list(replies), platforms=["twitter"],
        status=ContentStatus.SCHEDULED.value, post_bridge_post_id=PB_ID, published_via=PUBLISHED_VIA_DUCT,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    queue.posts[PB_ID] = {"id": PB_ID, "caption": caption, "status": "scheduled", "scheduled_at": WHEN}
    return row


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _edit(db, owner, post, **fields):
    """What the post viewport sends: every editable field, changed or not."""
    body = {"caption": post.caption, "replies": post.replies, "platforms": post.platforms,
            "status": post.status, **fields}
    return _api(db, owner).patch(f"/api/content/posts/{post.id}", json=body)


# ---------------------------------------------------------------------------
# Publishing: PostBridge's statuses
# ---------------------------------------------------------------------------


def _publish_now(db, project, owner, queue, status: str):
    queue.create_status = status
    post = ContentPost(project_id=project.id, post_dir_slug="2026-09-28-002", post_type=TEXT_POST_TYPE,
                       caption="Now.", replies=[], platforms=["twitter"], status="draft")
    db.add(post)
    db.commit()
    db.refresh(post)
    return post, _api(db, owner).post(f"/api/content/posts/{post.id}/publish", json={"social_account_ids": [101]})


def test_a_post_going_out_now_is_posted_not_filed_under_processing(db, project, owner, queue):
    """The board has no column for PostBridge's `processing`; a post filed
    under it disappeared from the board."""
    post, res = _publish_now(db, project, owner, queue, "processing")

    assert res.status_code == 200, res.text
    db.refresh(post)
    assert post.status == ContentStatus.POSTED and post.posted_at is not None


def test_a_post_postbridge_failed_is_reported_and_stays_a_draft(db, project, owner, queue):
    post, res = _publish_now(db, project, owner, queue, "failed")

    assert res.status_code == 502
    assert "needs reconnecting" in res.json()["detail"]
    db.refresh(post)
    assert post.status == "draft" and post.post_bridge_post_id == ""


# ---------------------------------------------------------------------------
# Editing a queued post
# ---------------------------------------------------------------------------


def test_new_words_reach_the_queue_with_the_time_they_were_due(db, project, owner, queue):
    post = _queued(db, project, queue)

    res = _edit(db, owner, post, caption="Shipped the eval gate. Twice.", replies=["Source: the CI run."])

    assert res.status_code == 200, res.text
    assert queue.calls() == [("GET", f"/v1/posts/{PB_ID}"), ("PATCH", f"/v1/posts/{PB_ID}")]
    _, _, sent = queue.requests[-1]
    # Without the time, PostBridge would publish the post the moment it got the edit.
    assert sent["scheduled_at"] == WHEN
    assert sent["caption"] == "Shipped the eval gate. Twice."
    assert sent["platform_configurations"]["twitter"] == {"first_comment": "Source: the CI run."}
    db.refresh(post)
    assert post.caption == "Shipped the eval gate. Twice." and post.status == ContentStatus.SCHEDULED


def test_a_save_that_changes_no_words_does_not_call_postbridge(db, project, owner, queue):
    """The viewport resends every field on every save."""
    post = _queued(db, project, queue)

    assert _edit(db, owner, post, hook_text="internal note").status_code == 200
    assert queue.requests == []


def test_an_edit_postbridge_refuses_is_not_saved(db, project, owner, queue):
    post = _queued(db, project, queue)
    queue.down = True

    res = _edit(db, owner, post, caption="New words.")

    assert res.status_code == 502
    db.refresh(post)
    assert post.caption == "Shipped the eval gate."


def test_an_edit_to_a_post_already_out_is_refused_and_the_post_is_marked_posted(db, project, owner, queue):
    post = _queued(db, project, queue)
    queue.posts[PB_ID]["status"] = "posted"

    res = _edit(db, owner, post, caption="Too late.")

    assert res.status_code == 409
    assert "already went out on Twitter / X" in res.json()["detail"]
    assert ("PATCH", f"/v1/posts/{PB_ID}") not in queue.calls()
    db.refresh(post)
    assert post.caption == "Shipped the eval gate." and post.status == ContentStatus.POSTED


def test_a_post_postbridge_no_longer_holds_is_saved_as_a_draft(db, project, owner, queue):
    """Deleted in PostBridge's own dashboard: the edit saves and the post
    stops claiming a slot it does not have."""
    post = _queued(db, project, queue)
    del queue.posts[PB_ID]

    res = _edit(db, owner, post, caption="Still want this.")

    assert res.status_code == 200, res.text
    db.refresh(post)
    assert post.caption == "Still want this."
    assert post.status == ContentStatus.DRAFT and post.post_bridge_post_id == "" and post.scheduled_at is None


def test_unscheduling_takes_the_post_off_the_queue(db, project, owner, queue):
    post = _queued(db, project, queue)

    res = _edit(db, owner, post, status=ContentStatus.DISCARDED.value)

    assert res.status_code == 200, res.text
    assert queue.calls() == [("DELETE", f"/v1/posts/{PB_ID}")]
    assert PB_ID not in queue.posts
    db.refresh(post)
    assert post.status == ContentStatus.DISCARDED and post.post_bridge_post_id == ""


# ---------------------------------------------------------------------------
# Deleting a queued post
# ---------------------------------------------------------------------------


def test_deleting_a_queued_post_deletes_it_at_postbridge_first(db, project, owner, queue):
    post = _queued(db, project, queue)
    post_id = post.id

    res = _api(db, owner).delete(f"/api/content/posts/{post_id}")

    assert res.status_code == 200, res.text
    assert PB_ID not in queue.posts
    db.expire_all()
    assert db.get(ContentPost, post_id) is None


def test_deleting_a_post_already_out_keeps_the_row_and_says_where_to_delete_it(db, project, owner, queue):
    post = _queued(db, project, queue)
    queue.posts[PB_ID]["status"] = "posted"

    res = _api(db, owner).delete(f"/api/content/posts/{post.id}")

    assert res.status_code == 409
    assert "Delete it on Twitter / X" in res.json()["detail"]
    db.refresh(post)
    assert post.status == ContentStatus.POSTED
    # Now it is only a record here, so a second delete removes it.
    assert _api(db, owner).delete(f"/api/content/posts/{post.id}").status_code == 200


# ---------------------------------------------------------------------------
# The agent rewriting a queued post
# ---------------------------------------------------------------------------


def test_the_agents_rewrite_of_a_queued_post_reaches_the_queue(engine, db, project, queue, monkeypatch):
    post = _queued(db, project, queue)
    session = make_session("sched-1", project.id, "draft_post")
    session.post_id = post.id
    session.channel = "twitter"
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))

    async def _emit(_event):
        return None

    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, _emit, session)}
    result = json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": {
        "type": "post", "project_id": str(project.id), "post_dir_slug": "2026-09-28-001",
        "pillar": "build", "topic": "The eval gate", "caption": "Shipped the eval gate, finally.",
        "replies": ["Source: our CI logs."],
    }})))

    assert result.get("status") != "error", result
    _, _, sent = queue.requests[-1]
    assert (sent["caption"], sent["scheduled_at"]) == ("Shipped the eval gate, finally.", WHEN)
    assert sent["platform_configurations"]["twitter"] == {"first_comment": "Source: our CI logs."}
    db.expire_all()
    assert db.get(ContentPost, post.id).status == ContentStatus.SCHEDULED

