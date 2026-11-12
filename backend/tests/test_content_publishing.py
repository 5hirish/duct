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
from agents.content.publishing import SLIDE_RENDER, WHY_PUBLISHES
from agents.content.schema import ContentStatus, make_session
from agents.core.events import AgentEvent
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentAsset, ContentPost, ContentSocialLink
from models.membership import ProjectMember
from models.project import Project
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine
from tests.fakes import Approver, PostBridgeQueue, connect_scheduler

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
def queue(monkeypatch, db, owner) -> PostBridgeQueue:
    q = PostBridgeQueue()
    connect_scheduler(monkeypatch, db, owner.id, q.publisher)
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
    db.add(ContentSocialLink(project_id=project.id, publisher="post_bridge", external_account_id=str(account_id),
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


_APPROVE = object()


def _agent_publish(engine, project, post, monkeypatch, *, pause=_APPROVE, **args) -> dict:
    """The agent's publish, with a person who says yes unless told otherwise."""
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))
    session = make_session("publish-1", project.id, "draft_post")
    session.post_id = post.id

    async def emit(_event):
        return None

    approver = Approver() if pause is _APPROVE else pause
    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, emit, session, pause=approver)}
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
    post.status, post.publisher_post_id = "draft", ""
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


# --- the person approves every send --------------------------------------------
#
# The agent reads web pages, search results and strangers' captions. A
# sentence in any of them could otherwise publish a post early, so every send
# waits for a yes on a card that says what goes out, where and when.


def test_the_agent_publishes_only_after_a_yes_on_a_card_saying_what_goes_out(
    engine, db, project, slideshow, queue, monkeypatch,
):
    approver = Approver()

    result = _agent_publish(engine, project, slideshow, monkeypatch, pause=approver,
                            social_account_ids=[101], scheduled_at="2026-11-02T09:00:00+01:00")

    assert result.get("status") != "error", result
    [(event, card)] = approver.asked
    assert event == AgentEvent.TOOL_APPROVAL_REQUIRED
    assert card["why"] == WHY_PUBLISHES and card["tool"] == "publish_post"
    shown = json.loads(card["arguments"])
    assert shown["accounts"] == ["101"] and shown["when"] == "2026-11-02T09:00:00+01:00"
    assert shown["caption"] == "Morning ritual" and shown["media"] == ["slide-01.png", "slide-02.png"]
    assert queue.created()["scheduled_at"] == "2026-11-02T08:00:00Z"


def test_the_card_shows_the_whole_caption_and_every_reply_that_goes_out(
    engine, db, project, slideshow, queue, monkeypatch,
):
    slideshow.caption = "word " * 300
    slideshow.replies = ["First reply, with the link", "Second reply"]
    db.add(slideshow)
    db.commit()
    approver = Approver(approved=False)

    _agent_publish(engine, project, slideshow, monkeypatch, pause=approver, social_account_ids=[101])

    shown = json.loads(approver.asked[0][1]["arguments"])
    assert shown["caption"] == "word " * 300
    published = shown["replies"]
    assert published == ["First reply, with the link", "Second reply"][: len(published)]
    assert len(published) + shown["replies_you_post_by_hand"] == 2


def test_a_yes_for_an_older_version_of_the_post_sends_nothing(
    engine, db, project, slideshow, queue, monkeypatch,
):
    # A resumed thread re-reads the post: an edit made after the card appeared
    # gives a different print than the one approved, and goes back to the person.
    result = _agent_publish(engine, project, slideshow, monkeypatch,
                            pause=Approver(fingerprint="the card before the edit"), social_account_ids=[101])

    assert result["status"] == "error" and "changed" in result["message"]
    assert queue.requests == [] and queue.uploads == []


def test_the_print_moves_with_every_word_that_goes_out(slideshow):
    from agents.content.publishing import publish_card
    from service.publishers.registry import spec_for

    spec = spec_for("post_bridge")
    before = publish_card(slideshow, spec, ["101"], None, tiktok_draft=False, files=[])["fingerprint"]
    slideshow.caption = "Morning ritual, now with a link"

    assert publish_card(slideshow, spec, ["101"], None, tiktok_draft=False, files=[])["fingerprint"] != before


def test_a_no_on_the_card_sends_nothing_and_leaves_the_post_a_draft(
    engine, db, project, slideshow, queue, monkeypatch,
):
    result = _agent_publish(engine, project, slideshow, monkeypatch, pause=Approver(approved=False),
                            social_account_ids=[101])

    assert result["status"] == "skipped"
    assert queue.requests == [] and queue.uploads == []
    db.refresh(slideshow)
    assert slideshow.status == "draft"


def test_with_nobody_to_ask_nothing_is_sent(engine, db, project, slideshow, queue, monkeypatch):
    result = _agent_publish(engine, project, slideshow, monkeypatch, pause=None, social_account_ids=[101])

    assert result["status"] == "needs_approval"
    assert queue.requests == []


def test_a_post_that_cannot_go_out_is_never_put_to_the_person(engine, db, project, queue, monkeypatch):
    unrendered = ContentPost(project_id=project.id, post_dir_slug="2026-10-31-009", post_type="slideshow",
                             caption="No renders", platforms=["tiktok"], status="draft",
                             slides=[{"slide_id": "s1", "kind": "collage"}])
    db.add(unrendered)
    db.commit()
    db.refresh(unrendered)
    approver = Approver()

    result = _agent_publish(engine, project, unrendered, monkeypatch, pause=approver, social_account_ids=[101])

    assert result["status"] == "error"
    assert approver.asked == []


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
