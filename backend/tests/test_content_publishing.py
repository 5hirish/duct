"""What a post sends to PostBridge, from which account, and when.

The Publish button and the agent's ``publish_post`` used to choose media each
their own way: the button read only ``/uploads/`` files off local disk, so on
hosted Duct (pictures on R2) it found nothing, and elsewhere it sent every raw
image beside the composed slides. The agent could not publish at all without
account ids no tool would give it. And a scheduled time went out without its
zone. These run both publish paths against the real PostBridge client over a
faked transport, with storage serving R2-style absolute URLs.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import agents.content.tools as content_tools
import routes.content as content_routes
import service.auth as auth_service
import service.post_bridge as post_bridge
from agents.content.publishing import SLIDE_RENDER
from agents.content.schema import ContentStatus, make_session
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentAsset, ContentPost, ContentSocialLink
from models.membership import ProjectMember
from models.project import Project
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine
from tests.fakes import PostBridgeQueue

CDN = "https://media.duct.test/projects/p1"


# --- fixtures ------------------------------------------------------------------


@pytest.fixture
def engine():
    return make_sqlite_engine()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def owner(db):
    row = User(email="publisher@example.com")
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


@pytest.fixture
def r2(monkeypatch) -> dict[str, bytes]:
    """The bucket behind the CDN: an absolute URL is read over HTTP, which is
    the read the old route never made."""
    bucket: dict[str, bytes] = {}

    def get(url, **_kwargs):
        if url not in bucket:
            return httpx.Response(404, request=httpx.Request("GET", url))
        return httpx.Response(200, content=bucket[url], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    return bucket


def _asset(db, post, r2, name, *, slide_id="", render=False, at=0) -> ContentAsset:
    url = f"{CDN}/{'renders' if render else 'generated'}/{name}"
    r2[url] = f"bytes of {name}".encode()
    row = ContentAsset(
        project_id=post.project_id, post_id=post.id, url=url, filename=name, mime_type="image/png",
        asset_type=SLIDE_RENDER if render else "generated", source="render" if render else "gemini",
        params={"slide_id": slide_id} if render else {},
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(seconds=at),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def slideshow(db, project, r2) -> ContentPost:
    """Two photo slides, each with its raw image and its composed render."""
    post = ContentPost(project_id=project.id, post_dir_slug="2026-10-31-001", post_type="slideshow",
                       caption="Morning ritual", platforms=["tiktok"], status="draft")
    db.add(post)
    db.commit()
    db.refresh(post)
    raw1 = _asset(db, post, r2, "raw-1.png", at=0)
    raw2 = _asset(db, post, r2, "raw-2.png", at=1)
    _asset(db, post, r2, "slide-02.png", slide_id="slide-02", render=True, at=2)
    _asset(db, post, r2, "slide-01.png", slide_id="slide-01", render=True, at=3)
    post.slides = [
        {"slide_id": "slide-01", "kind": "photo", "image_url": raw1.url},
        {"slide_id": "slide-02", "kind": "photo", "image_url": raw2.url},
    ]
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def _link(db, project, account_id: int, platform: str, username: str) -> None:
    db.add(ContentSocialLink(project_id=project.id, external_account_id=str(account_id),
                             platform=platform, username=username))
    db.commit()


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _publish(db, owner, post, **body):
    return _api(db, owner).post(f"/api/content/posts/{post.id}/publish",
                                json={"social_account_ids": [101], **body})


def _agent_publish(engine, project, post, monkeypatch, **args) -> dict:
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))
    session = make_session("publish-1", project.id, "draft_post")
    session.post_id = post.id

    async def emit(_event):
        return None

    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, emit, session)}
    return json.loads(asyncio.run(tools["publish_post"].ainvoke({"post_id": str(post.id), **args})))


def _sent(queue) -> list[tuple[str, bytes]]:
    return [(u["name"], u["bytes"]) for u in queue.uploads]


# --- the media -----------------------------------------------------------------


def test_the_button_publishes_pictures_stored_on_r2(db, owner, slideshow, queue):
    res = _publish(db, owner, slideshow)

    assert res.status_code == 200, res.text
    assert res.json()["status"] == ContentStatus.SCHEDULED
    assert queue.created()["media"] == ["m1", "m2"]


def test_composed_slides_go_in_slide_order_and_the_raw_photos_stay_behind(db, owner, slideshow, queue):
    assert _publish(db, owner, slideshow).status_code == 200

    assert _sent(queue) == [("slide-01.png", b"bytes of slide-01.png"), ("slide-02.png", b"bytes of slide-02.png")]


def test_the_agent_sends_exactly_what_the_button_does(engine, db, project, slideshow, queue, monkeypatch):
    result = _agent_publish(engine, project, slideshow, monkeypatch, social_account_ids=[101])

    assert result.get("status") != "error", result
    assert result["media_count"] == 2
    assert [name for name, _ in _sent(queue)] == ["slide-01.png", "slide-02.png"]


def test_a_person_publishes_an_unrendered_photo_slide_as_its_photo_but_not_a_collage(db, owner, project, r2, queue):
    post = ContentPost(project_id=project.id, post_dir_slug="2026-10-31-002", post_type="slideshow",
                       caption="Two looks", platforms=["tiktok"], status="draft")
    db.add(post)
    db.commit()
    db.refresh(post)
    photo = _asset(db, post, r2, "photo.png")
    post.slides = [{"slide_id": "slide-01", "kind": "photo", "image_url": photo.url}]
    db.add(post)
    db.commit()

    assert _publish(db, owner, post).status_code == 200
    assert _sent(queue) == [("photo.png", b"bytes of photo.png")]

    queue.uploads.clear()
    post.status, post.post_bridge_post_id = "draft", ""
    post.slides = [*post.slides, {"slide_id": "slide-02", "kind": "collage",
                                  "items": [{"image_url": photo.url}, {"image_url": photo.url}]}]
    db.add(post)
    db.commit()

    res = _publish(db, owner, post)
    assert res.status_code == 400
    assert "slide-02" in res.json()["detail"]
    assert queue.uploads == []


def test_a_picture_storage_cannot_read_stops_the_publish_before_anything_uploads(db, owner, slideshow, queue, r2):
    r2.pop(f"{CDN}/renders/slide-02.png")

    res = _publish(db, owner, slideshow)

    assert res.status_code == 500
    assert queue.requests == []


# --- the account -----------------------------------------------------------------


def test_the_agent_posts_from_the_account_the_project_linked_for_the_platform(
    engine, db, project, slideshow, queue, monkeypatch,
):
    _link(db, project, 202, "linkedin", "kestrel-co")
    _link(db, project, 101, "tiktok", "kestrel.studio")

    result = _agent_publish(engine, project, slideshow, monkeypatch)

    assert result.get("status") != "error", result
    assert queue.created()["social_accounts"] == [101]


def test_two_linked_accounts_for_the_platform_are_named_not_guessed(
    engine, db, project, slideshow, queue, monkeypatch,
):
    _link(db, project, 101, "tiktok", "kestrel.studio")
    _link(db, project, 102, "tiktok", "kestrel.behind")

    result = _agent_publish(engine, project, slideshow, monkeypatch)

    assert result["status"] == "error"
    assert "@kestrel.studio" in result["message"] and "id 102" in result["message"]
    assert queue.requests == []


def test_no_linked_account_for_the_platform_says_where_to_link_one(
    engine, db, project, slideshow, queue, monkeypatch,
):
    _link(db, project, 202, "linkedin", "kestrel-co")

    result = _agent_publish(engine, project, slideshow, monkeypatch)

    assert result["status"] == "error"
    assert "TikTok" in result["message"] and "Content → Accounts" in result["message"]
    assert queue.requests == []


# --- the time ---------------------------------------------------------------------


@pytest.mark.parametrize("picked, due", [
    ("2026-11-02T09:00:00+01:00", "2026-11-02T08:00:00Z"),   # 9:00 in Madrid
    ("2026-11-02T09:00:00", "2026-11-02T09:00:00Z"),         # no zone: read as UTC
])
def test_a_scheduled_time_goes_out_as_the_instant_it_names(db, owner, slideshow, queue, picked, due):
    assert _publish(db, owner, slideshow, scheduled_at=picked).status_code == 200

    assert queue.created()["scheduled_at"] == due
    db.refresh(slideshow)
    assert slideshow.scheduled_at == datetime.fromisoformat(due)


def test_the_agents_scheduled_time_keeps_its_offset_too(engine, db, project, slideshow, queue, monkeypatch):
    result = _agent_publish(engine, project, slideshow, monkeypatch,
                            social_account_ids=[101], scheduled_at="2026-11-02T09:00:00+01:00")

    assert result.get("status") != "error", result
    assert queue.created()["scheduled_at"] == "2026-11-02T08:00:00Z"
