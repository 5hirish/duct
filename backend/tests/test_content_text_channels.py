"""X and LinkedIn as text-first channels (issue #269).

One post row serves every platform; what differs is the channel's rules
(agents/content/channels.RULES). These tests hold the three places that read
them to the same answer: the agent's writer, the two publish paths, and the
pre-publish review. PostBridge runs for real against a faked transport, so the
request that would have gone over the wire is what gets asserted.
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
import service.post_bridge as post_bridge
from agents.content.assessment import compute_sanity
from agents.content.channels import brand_platforms
from agents.content.performance import rank_types
from agents.content.publishing import PUBLISHED_VIA_DUCT, publish_blockers
from agents.content.schema import SanityCheckId, TEXT_POST_TYPE
from agents.content.v1.runner import make_session
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentPost
from models.membership import ProjectMember
from models.project import Project
from service.membership import ROLE_OWNER
from service.post_bridge import PostBridgeClient
from tests.conftest import make_sqlite_engine

WHEN = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


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


def _text_post(db, project, *, platforms=("twitter",), replies=(), caption="Shipped the eval gate. It failed us twice.", slug="2026-09-28-001") -> ContentPost:
    row = ContentPost(
        project_id=project.id,
        post_dir_slug=slug,
        post_type=TEXT_POST_TYPE,
        caption=caption,
        replies=list(replies),
        platforms=list(platforms),
        status="draft",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class PostBridgeWire:
    """PostBridge's API as a transport: records every request, answers a
    create with a scheduled post."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if req.url.path == "/v1/posts":
            body = json.loads(req.read())
            return httpx.Response(200, json={
                "id": "pb_post_1", "caption": body["caption"], "status": "scheduled",
                "social_accounts": body["social_accounts"], "is_draft": False,
                "scheduled_at": body.get("scheduled_at"),
            })
        raise AssertionError(f"unexpected PostBridge call: {req.method} {req.url.path}")

    def client(self, *_args) -> PostBridgeClient:
        return PostBridgeClient("sk-fake", client=httpx.AsyncClient(transport=httpx.MockTransport(self)))

    def created(self) -> dict:
        (create,) = [r for r in self.requests if r.url.path == "/v1/posts"]
        return json.loads(create.read())


@pytest.fixture
def wire(monkeypatch) -> PostBridgeWire:
    w = PostBridgeWire()
    monkeypatch.setattr(post_bridge, "client_for_user", w.client)
    return w


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _tools(session, engine, monkeypatch, emitted: list | None = None) -> dict:
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))

    async def _emit(event):
        if emitted is not None:
            emitted.append(event)

    return {t.name: t for t in content_tools.build_content_tools_lc(session.project_id, _emit, session)}


def _draft(project, **extra) -> dict:
    return {
        "type": "post",
        "project_id": str(project.id),
        "post_dir_slug": "2026-09-28-001",
        "pillar": "build",
        "topic": "Why our eval gate fails twice before it passes",
        **extra,
    }


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


def test_a_draft_with_no_platforms_is_filed_under_the_sessions_channel(engine, db, project, monkeypatch):
    """A model that leaves `platforms` out must not turn an X draft into a
    TikTok post by the schema's default; with no slides it is a text post."""
    session = make_session("text-1", project.id, "draft_post")
    session.channel = "twitter"
    emitted: list = []
    tools = _tools(session, engine, monkeypatch, emitted)

    result = json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": _draft(
        project, caption="Shipped the eval gate. It failed us twice.", replies=["Why it matters: ...", "  "],
    )})))

    assert result.get("status") != "error", result
    row = db.get(ContentPost, session.post_id)
    assert row.post_type == TEXT_POST_TYPE
    assert row.platforms == ["twitter"]
    assert row.replies == ["Why it matters: ..."]   # a blank reply is not a reply
    (update,) = [e for e in emitted if e.get("post_id")]
    channel = update["payload"]["channel"]
    assert channel["id"] == "twitter" and channel["max_chars"] == 280 and channel["publishable_replies"] == 1


def test_an_over_length_tweet_is_refused_and_nothing_is_saved(engine, db, project, monkeypatch):
    session = make_session("text-2", project.id, "draft_post")
    session.channel = "twitter"
    tools = _tools(session, engine, monkeypatch)

    result = json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": _draft(project, caption="x" * 281)})))

    assert result["status"] == "error"
    assert "281 characters; Twitter / X allows 280" in result["message"]
    assert session.post_id is None


def test_the_same_words_fit_linkedin(engine, db, project, monkeypatch):
    session = make_session("text-3", project.id, "draft_post")
    session.channel = "linkedin"
    tools = _tools(session, engine, monkeypatch)

    result = json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": _draft(project, caption="x" * 281)})))

    assert result.get("status") != "error", result
    assert db.get(ContentPost, session.post_id).platforms == ["linkedin"]


# ---------------------------------------------------------------------------
# Publishing — both paths, one request shape
# ---------------------------------------------------------------------------


def test_the_publish_route_sends_a_text_post_as_words_with_its_first_reply(db, project, owner, wire):
    post = _text_post(db, project, replies=["The source: our CI logs."])

    res = _api(db, owner).post(
        f"/api/content/posts/{post.id}/publish",
        json={"social_account_ids": [101], "scheduled_at": WHEN.isoformat()},
    )

    assert res.status_code == 200, res.text
    assert [r.url.path for r in wire.requests] == ["/v1/posts"]   # nothing uploaded
    body = wire.created()
    assert "media" not in body
    assert body["caption"] == post.caption
    assert body["platform_configurations"]["twitter"] == {"first_comment": "The source: our CI logs."}
    db.refresh(post)
    assert post.status == "scheduled" and post.published_via == PUBLISHED_VIA_DUCT
    assert post.scheduled_at is not None


def test_the_agents_publish_records_the_schedule_the_route_always_did(engine, db, project, wire, monkeypatch):
    """#272: the tool never wrote scheduled_at or published_via, so a post
    the agent scheduled never reached its date on the calendar."""
    post = _text_post(db, project)
    session = make_session("text-4", project.id, "draft_post")
    tools = _tools(session, engine, monkeypatch)

    result = json.loads(asyncio.run(tools["publish_post"].ainvoke({
        "post_id": str(post.id), "social_account_ids": [101], "scheduled_at": WHEN.isoformat(),
    })))

    assert result["status"] == "scheduled", result
    db.refresh(post)
    assert post.status == "scheduled"
    assert post.published_via == PUBLISHED_VIA_DUCT
    assert post.scheduled_at is not None and post.scheduled_at.replace(tzinfo=timezone.utc) == WHEN


def test_a_thread_publishes_the_post_and_first_reply_and_counts_the_rest(engine, db, project, wire, monkeypatch):
    """PostBridge posts one reply on X. A longer thread still goes out — the
    post and its first reply — and the agent is told how many are left to post
    by hand, rather than the whole thread being refused."""
    post = _text_post(db, project, replies=["two", "three", "four"])
    session = make_session("text-5", project.id, "draft_post")
    tools = _tools(session, engine, monkeypatch)

    result = json.loads(asyncio.run(tools["publish_post"].ainvoke({
        "post_id": str(post.id), "social_account_ids": [101],
    })))

    assert result["replies_to_post_by_hand"] == 2
    assert wire.created()["platform_configurations"]["twitter"] == {"first_comment": "two"}


def test_a_linkedin_post_with_a_first_comment_still_publishes(db, project, owner, wire):
    """LinkedIn publishes no comments; the post goes out alone and the comment
    is the author's to paste. It must never block the post."""
    post = _text_post(db, project, platforms=("linkedin",), replies=["Source: our CI logs."])

    res = _api(db, owner).post(f"/api/content/posts/{post.id}/publish", json={"social_account_ids": [101]})

    assert res.status_code == 200, res.text
    assert "linkedin" not in (wire.created().get("platform_configurations") or {})


def test_a_link_in_the_tweet_itself_is_refused_and_the_reply_keeps_one(engine, db, project, monkeypatch):
    """PostBridge deletes every link from the post itself on X, bare domains
    included, and says nothing. The reply keeps its links, so that is where
    the refusal sends it."""
    session = make_session("text-6", project.id, "draft_post")
    session.channel = "twitter"
    tools = _tools(session, engine, monkeypatch)

    refused = json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": _draft(
        project, caption="We moved the docs to getduct.ai/docs today.",
    )})))
    kept = json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": _draft(
        project, caption="We moved the docs today. Node.js users, e.g. you, read the reply.",
        replies=["Here: https://getduct.ai/docs"],
    )})))

    assert refused["status"] == "error"
    assert "getduct.ai/docs" in refused["message"] and "reply" in refused["message"]
    assert kept.get("status") != "error", kept


def test_the_publish_route_holds_a_typed_link_back_from_x_but_not_linkedin(db, project, owner, wire):
    tweet = _text_post(db, project, caption="Read it at https://getduct.ai/blog/evals.")
    post = _text_post(db, project, platforms=("linkedin",), caption="Read it at https://getduct.ai/blog/evals.", slug="2026-09-28-002")

    refused = _api(db, owner).post(f"/api/content/posts/{tweet.id}/publish", json={"social_account_ids": [101]})
    sent = _api(db, owner).post(f"/api/content/posts/{post.id}/publish", json={"social_account_ids": [101]})

    assert refused.status_code == 400 and "https://getduct.ai/blog/evals" in refused.json()["detail"]
    assert sent.status_code == 200, sent.text
    assert [r.url.path for r in wire.requests] == ["/v1/posts"]   # only LinkedIn's went out


def test_a_text_post_cannot_go_to_a_channel_that_needs_media():
    post = ContentPost(post_type=TEXT_POST_TYPE, caption="words", platforms=["tiktok"], slides=[], replies=[])
    assert any("without a picture or video" in p for p in publish_blockers(post))


def test_x_numbers_are_typed_in_not_synced(db, project, owner, wire):
    """PostBridge reports TikTok, YouTube, Instagram and Facebook only; a sync
    for an X post would return nothing, so the route says where the numbers
    come from instead of calling."""
    post = _text_post(db, project)
    post.post_bridge_post_id = "pb_post_1"
    db.add(post)
    db.commit()

    res = _api(db, owner).post(f"/api/content/posts/{post.id}/sync-metrics")

    assert res.status_code == 409
    assert "doesn't report Twitter / X numbers" in res.json()["detail"]
    assert wire.requests == []


# ---------------------------------------------------------------------------
# The review, the plan, the brand
# ---------------------------------------------------------------------------


def test_the_review_holds_x_to_its_own_limit_and_asks_for_no_hashtags():
    checks = {c.id: c for c in compute_sanity([], "x" * 281, [], replies=["fine"], channel="twitter")}

    assert not checks[SanityCheckId.CAPTION_LENGTH].passed
    assert checks[SanityCheckId.CAPTION_LENGTH].offenders == ["caption"]
    assert SanityCheckId.HASHTAGS_PRESENT not in checks
    assert checks[SanityCheckId.SLIDES_HAVE_IMAGES].passed   # no slides, nothing missing
    # A carousel keeps the cross-post ceiling and still wants hashtags.
    visual = {c.id: c for c in compute_sanity([], "x" * 281, [], channel="tiktok")}
    assert visual[SanityCheckId.CAPTION_LENGTH].passed
    assert not visual[SanityCheckId.HASHTAGS_PRESENT].passed


def test_a_visual_plan_never_explores_text():
    _, _, explore = rank_types([], None)
    assert TEXT_POST_TYPE not in explore


def test_the_brands_channels_become_platforms_the_crawl_calls_x_twitter():
    assert brand_platforms(["instagram", "x", "X", "mastodon", 3, "linkedin"]) == ["instagram", "twitter", "linkedin"]


def test_the_apps_draft_channels_are_the_backends_playbooks():
    """app/src/lib/contentEnums.js mirrors which channels a draft can be
    written for, and which are words first; the New post menu and the waiting
    copy read it. Every other number arrives on the post (`post.channel`)."""
    import re
    from pathlib import Path

    from agents.content.channels import PLAYBOOKS, TEXT_PLAYBOOKS, Platform

    source = (Path(__file__).resolve().parents[2] / "app" / "src" / "lib" / "contentEnums.js").read_text()
    block = source[source.index("export const DRAFT_CHANNELS"):]
    block = block[:block.index("]);")]
    app = {
        str(Platform[name]): flag == "true"
        for name, flag in re.findall(r"\{\s*id:\s*Platform\.(\w+),\s*textFirst:\s*(true|false)\s*\}", block)
    }
    assert app == {str(p): PLAYBOOKS[p] in TEXT_PLAYBOOKS for p in PLAYBOOKS}
