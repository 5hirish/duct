"""Schedulers are connectors (service/publishers/): PostBridge and Zernio.

Nothing publishes by default; a project publishes through the scheduler its
owner connected, and each linked account says which one holds it. Zernio runs
for real against a faked transport (tests/fakes.ZernioQueue), so the request
that would have gone over the wire is what gets asserted.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import agents.content.tools as content_tools
import routes.content as content_routes
import service.auth as auth_service
from agents.content.publishing import publish_blockers
from agents.content.schema import TEXT_POST_TYPE
from agents.content.v1.runner import make_session
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentPost, ContentSocialLink
from models.membership import ProjectMember
from models.project import Project
from service.content_metrics import metric_value
from service.membership import ROLE_OWNER
from service.post_bridge.publisher import POSTBRIDGE
from service.publishers import MediaRef, Outgoing, Target
from service.publishers.registry import NO_SCHEDULER
from service.zernio.publisher import ZERNIO
from tests.conftest import make_sqlite_engine
from tests.fakes import ZernioQueue, connect_scheduler, post_bridge_on

WHEN = datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    return make_sqlite_engine()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def owner(db):
    row = User(email="founder@example.com")
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
def zernio(monkeypatch, db, owner) -> ZernioQueue:
    q = ZernioQueue()
    connect_scheduler(monkeypatch, db, owner.id, q.publisher, publisher_id=ZERNIO.id)
    return q


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _post(db, project, *, platforms=("linkedin",), replies=(), caption="We shipped the eval gate.", **fields) -> ContentPost:
    row = ContentPost(
        project_id=project.id, post_dir_slug="2026-11-03-001", post_type=TEXT_POST_TYPE,
        caption=caption, replies=list(replies), platforms=list(platforms), status="draft", **fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _link(db, project, *, publisher, account_id, platform, username="kestrel"):
    db.add(ContentSocialLink(
        project_id=project.id, publisher=publisher, external_account_id=account_id,
        platform=platform, username=username,
    ))
    db.commit()


def _tools(project, engine, monkeypatch, channel="twitter"):
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))
    session = make_session("pub-1", project.id, "draft_post")
    session.channel = channel
    tools = content_tools.build_content_tools_lc(project.id, lambda e: asyncio.sleep(0), session)
    return {t.name: t for t in tools}


# --- nothing is a default -------------------------------------------------------


def test_nothing_publishes_until_a_scheduler_is_connected(db, project, owner):
    post = _post(db, project)
    c = _api(db, owner)

    res = c.post(f"/api/content/posts/{post.id}/publish", json={"social_account_ids": ["acc_li"]})

    assert res.status_code == 400 and res.json()["detail"] == NO_SCHEDULER
    listed = c.get("/api/content/publishers", params={"project_id": str(project.id)}).json()
    assert [(p["id"], p["connected"]) for p in listed] == [("post_bridge", False), ("zernio", False)]
    db.refresh(post)
    assert post.status == "draft" and post.publisher == ""


def test_the_accounts_of_every_connected_scheduler_are_listed_with_theirs(db, project, owner, zernio, monkeypatch):
    def post_bridge(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/social-accounts"
        return httpx.Response(200, json={"data": [{"id": 101, "platform": "tiktok", "username": "kestrel.tt"}]})

    connect_scheduler(monkeypatch, db, owner.id, post_bridge_on(post_bridge))

    accounts = _api(db, owner).get("/api/content/social-accounts", params={"project_id": str(project.id)}).json()

    by_id = {a["id"]: a for a in accounts}
    assert (by_id["101"]["publisher"], by_id["101"]["platform"]) == ("post_bridge", "tiktok")
    assert (by_id["acc_li"]["publisher"], by_id["acc_li"]["avatar_url"]) == ("zernio", "https://media.zernio.test/li.png")
    assert by_id["acc_x"]["needs_reconnect"] is True


# --- a post goes through the scheduler holding its account ------------------------


def test_a_linkedin_post_goes_out_through_zernio_with_its_first_comment(db, project, owner, zernio):
    _link(db, project, publisher="zernio", account_id="acc_li", platform="linkedin")
    post = _post(db, project, replies=["The write-up: https://getduct.ai/blog/evals"])

    res = _api(db, owner).post(
        f"/api/content/posts/{post.id}/publish",
        json={"social_account_ids": ["acc_li"], "scheduled_at": WHEN.isoformat()},
    )

    assert res.status_code == 200, res.text
    assert zernio.created()["platforms"] == [{
        "platform": "linkedin", "accountId": "acc_li",
        "platformSpecificData": {"firstComment": "The write-up: https://getduct.ai/blog/evals"},
    }]
    assert zernio.created()["scheduledFor"] == WHEN.isoformat() and "publishNow" not in zernio.created()
    body = res.json()
    assert (body["publisher"], body["publisher_post_id"], body["status"]) == ("zernio", ZernioQueue.POST_ID, "scheduled")
    assert body["channel"]["publishable_replies"] == 1 and body["channel"]["synced_metrics"] is True


def test_an_x_thread_goes_out_whole_on_zernio_and_keeps_its_link(db, engine, project, zernio, monkeypatch):
    _link(db, project, publisher="zernio", account_id="acc_x", platform="twitter", username="kestrelhq")
    post = _post(
        db, project, platforms=("twitter",), caption="Our docs moved to getduct.ai/docs today.",
        replies=["Why: one page per job.", "What broke: nothing."],
    )
    # PostBridge strips the link from an X post, so there it is a problem;
    # Zernio sends it, so there it is not.
    assert any("link" in p for p in publish_blockers(post, POSTBRIDGE))
    assert publish_blockers(post, ZERNIO) == []

    result = json.loads(asyncio.run(_tools(project, engine, monkeypatch)["publish_post"].ainvoke({"post_id": str(post.id)})))

    assert result.get("status") != "error", result
    (target,) = zernio.created()["platforms"]
    assert [item["content"] for item in target["platformSpecificData"]["threadItems"]] == [
        "Our docs moved to getduct.ai/docs today.", "Why: one page per job.", "What broke: nothing.",
    ]
    assert zernio.created()["publishNow"] is True
    assert result["publisher"] == "zernio" and result["replies_to_post_by_hand"] == 0


def test_a_post_zernio_failed_is_reported_and_not_recorded(db, project, owner, zernio):
    zernio.create_status = "failed"
    _link(db, project, publisher="zernio", account_id="acc_li", platform="linkedin")
    post = _post(db, project)

    res = _api(db, owner).post(f"/api/content/posts/{post.id}/publish", json={"social_account_ids": ["acc_li"]})

    assert res.status_code == 502 and "The account needs reconnecting." in res.json()["detail"]
    db.refresh(post)
    assert post.status == "draft" and post.publisher_post_id == ""


def test_pictures_go_up_through_the_presigned_url_and_ride_as_media_items(zernio):
    async def go():
        async with zernio.publisher() as pub:
            ref = await pub.upload(b"\x89PNG", name="slide-01.png", mime_type="image/png")
            return ref, await pub.create_post(Outgoing(
                caption="Before and after.", targets=(Target("acc_li"),), media=(ref,), scheduled_at=WHEN,
            ))

    ref, remote = asyncio.run(go())

    assert zernio.uploads[0]["bytes"] == b"\x89PNG" and zernio.uploads[0]["content_type"] == "image/png"
    assert ref == MediaRef(id=f"https://{ZernioQueue.MEDIA_HOST}/1-slide-01.png", mime_type="image/png")
    assert zernio.created()["mediaItems"] == [{"url": ref.id, "type": "image"}]
    # The account's platform was looked up, because Zernio needs it and the caller had only the id.
    assert zernio.created()["platforms"][0]["platform"] == "linkedin"
    assert remote.status == "scheduled"


# --- a queued post, kept in step ---------------------------------------------------


def _queued(db, project) -> ContentPost:
    post = _post(
        db, project, publisher="zernio", publisher_post_id=ZernioQueue.POST_ID, published_via="duct",
        replies=["Sources in the comments."],
    )
    post.status = "scheduled"
    db.add(post)
    db.commit()
    return post


def _hold(zernio, status="scheduled"):
    zernio.posts[ZernioQueue.POST_ID] = {
        "_id": ZernioQueue.POST_ID, "content": "We shipped the eval gate.", "status": status,
        "scheduledFor": WHEN.isoformat(), "platforms": [{"platform": "linkedin", "accountId": "acc_li", "status": "pending"}],
    }


def test_an_edit_to_a_queued_zernio_post_reaches_it_with_its_time(db, project, owner, zernio):
    _hold(zernio)
    post = _queued(db, project)

    res = _api(db, owner).patch(f"/api/content/posts/{post.id}", json={"caption": "We shipped the eval gate today."})

    assert res.status_code == 200, res.text
    ((_, _, put),) = [r for r in zernio.requests if r[0] == "PUT"]
    assert put["content"] == "We shipped the eval gate today." and put["scheduledFor"] == WHEN.isoformat()
    assert put["platforms"][0]["platformSpecificData"] == {"firstComment": "Sources in the comments."}


def test_deleting_a_post_zernio_already_published_keeps_the_row(db, project, owner, zernio):
    _hold(zernio, status="published")
    post = _queued(db, project)

    res = _api(db, owner).delete(f"/api/content/posts/{post.id}")

    assert res.status_code == 409
    assert not [r for r in zernio.requests if r[0] == "DELETE"]   # asked first, never deleted
    db.refresh(post)
    assert post.status == "posted"


# --- its numbers -------------------------------------------------------------------


def test_zernio_numbers_land_in_perf_and_an_unreported_zero_stays_unknown(db, project, owner, zernio):
    post = _post(db, project, platforms=("instagram",), publisher="zernio", publisher_post_id="zp_9", published_via="duct")
    post.status = "posted"
    db.add(post)
    db.commit()
    zernio.analytics["zp_9"] = {
        "postId": "zp_9", "platform": "instagram", "platformPostUrl": "https://instagram.com/p/abc",
        "analytics": {"views": 900, "likes": 40, "comments": 3, "shares": 2, "saves": 0, "reach": 0,
                      "igReelsAvgWatchTime": 4500, "completionRate": 0.31, "lastUpdated": "2026-11-03T08:00:00Z"},
    }
    zernio.timeline["zp_9"] = [{"date": "2026-11-02", "platform": "instagram", "views": 700, "likes": 30}]

    res = _api(db, owner).post(f"/api/content/posts/{post.id}/sync-metrics")

    assert res.status_code == 200, res.text
    perf = res.json()["perf"]
    assert (metric_value(perf, "views"), metric_value(perf, "likes")) == (900, 40)
    assert metric_value(perf, "saves") is None and metric_value(perf, "reach") is None
    assert (metric_value(perf, "avg_watch_time"), metric_value(perf, "completion_rate")) == (4.5, 31.0)
    assert res.json()["daily_perf"] == [
        {"snapshot_date": "2026-11-02", "view_count": 700, "like_count": 30, "comment_count": 0, "share_count": 0},
    ]


def test_x_numbers_not_synced_yet_say_they_are_opt_in_on_zernio(db, project, owner, zernio):
    post = _post(db, project, platforms=("twitter",), publisher="zernio", publisher_post_id="zp_x", published_via="duct")
    post.status = "posted"
    db.add(post)
    db.commit()

    res = _api(db, owner).post(f"/api/content/posts/{post.id}/sync-metrics")

    assert res.status_code == 409 and "turn them on" in res.json()["detail"]
