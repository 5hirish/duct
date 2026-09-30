"""Video posts in the Content Studio (issue #284), from the tool to publishing.

The backends are faked at ``service.videos.video_client_for`` (their own
request shapes are pinned in ``tests/test_video_backends.py``); everything
from there on is real — the SQLite schema, the local object store, the post
lock, the events the stream carries, the routes a member calls.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import agents.content.tools as content_tools
import routes.content as content_routes
import service.auth as auth_service
import service.post_bridge as post_bridge
import service.videos as videos
from agents import engines
from agents.content.events import ContentEvent
from agents.content.schema import make_session
from agents.core.activity import ACTIVITY_TOOLS, ActivityKind
from agents.core.events import AgentEvent, StepStatus
from agents.models import Provider, VideoModel
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentAsset, ContentPost
from models.membership import ProjectMember
from models.project import Project
from service import storage
from service.membership import ROLE_OWNER
from service.videos import GeneratedVideo, VideoAPIError, VideoErrorCode
from tests.conftest import make_sqlite_engine

CLIP = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


# --- fixtures ------------------------------------------------------------------


@pytest.fixture
def engine():
    return make_sqlite_engine()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage, "get_configs", lambda: cfg)
    return tmp_path


def _user(db, email) -> User:
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def owner(db):
    return _user(db, "video-owner@example.com")


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
def post(db, project):
    row = ContentPost(project_id=project.id, post_dir_slug="kettle-day", caption="Morning ritual")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class FakeVideos:
    """Stands in for every video backend; records what the tool asked for."""

    def __init__(self, *, cost=None, error=None):
        self.calls: list[dict] = []
        self._cost = cost
        self._error = error

    def client_for(self, provider, api_key):
        fake = self

        class _Client:
            async def generate_video(self, request, *, first_frame=None, last_frame=None):
                fake.calls.append({
                    "provider": provider, "key": api_key, "request": request,
                    "first_frame": first_frame, "last_frame": last_frame,
                })
                if fake._error is not None:
                    raise fake._error
                return GeneratedVideo(data=CLIP, cost_usd=fake._cost)

        return _Client()


@pytest.fixture
def fake_videos(monkeypatch):
    fake = FakeVideos()
    monkeypatch.setattr(videos, "video_client_for", fake.client_for)
    return fake


def _session(project, post, provider=Provider.GOOGLE_GENAI, model=""):
    session = make_session("video-1", project.id, "draft_post")
    session.post_id = post.id
    session.video_provider = provider
    session.video_api_key = "key-video"
    session.video_model = model
    return session


def _generate(session, engine, monkeypatch, emitted=None, **args) -> dict:
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))
    events = emitted if emitted is not None else []

    async def emit(event):
        events.append(event)

    tools = {t.name: t for t in content_tools.build_content_tools_lc(session.project_id, emit, session)}
    return json.loads(asyncio.run(tools["generate_video"].ainvoke({"prompt": "a kettle boils", **args})))


def _image_asset(db, project, url="/uploads/kf.png") -> ContentAsset:
    row = ContentAsset(project_id=project.id, asset_type="generated", url=url, mime_type="image/png")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- the tool ------------------------------------------------------------------


def test_the_tool_declines_without_a_video_key_and_names_both_that_would_work(project, post):
    session = make_session("video-0", project.id, "draft_post")
    session.post_id = post.id
    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, lambda e: None, session)}
    result = asyncio.run(tools["generate_video"].ainvoke({"prompt": "x"}))
    assert "Gemini" in result and "OpenRouter" in result and "Providers" in result


def test_a_clip_becomes_the_posts_cut_and_its_cost_is_billed(
    db, engine, project, post, uploads, fake_videos, monkeypatch,
):
    events: list[dict] = []
    result = _generate(_session(project, post), engine, monkeypatch, events, duration_seconds=10)

    # Veo 3.1 Lite makes 8 s at most, $0.05/s at 720p — and the result says so.
    assert result["model"] == VideoModel.VEO_3_1_LITE.value
    assert result["duration_seconds"] == 8 and result["cost_usd"] == 0.40
    assert result["notes"] and result["attached_to_post"] == str(post.id)

    db.refresh(post)
    assert post.post_type == "video"
    assert post.video["asset_id"] == result["asset_id"] and post.video["cost_usd"] == 0.40
    asset = db.get(ContentAsset, UUID(result["asset_id"]))
    assert asset.mime_type == "video/mp4" and asset.filename.endswith(".mp4")
    assert (uploads / asset.url.removeprefix("/uploads/")).read_bytes() == CLIP

    (draft,) = [e for e in events if e["event"] == ContentEvent.POST_DRAFT_UPDATED]
    assert draft["payload"]["post_type"] == "video"
    assert [t["asset_id"] for t in draft["payload"]["video_takes"]] == [result["asset_id"]]
    (usage,) = [e for e in events if e["event"] == AgentEvent.TOKEN_USAGE]
    assert usage["scope"] == "media" and usage["cost_usd"] == 0.40 and usage["input_tokens"] == 0


def test_the_cost_openrouter_reports_is_the_cost(db, engine, project, post, uploads, monkeypatch):
    fake = FakeVideos(cost=0.1512)
    monkeypatch.setattr(videos, "video_client_for", fake.client_for)
    result = _generate(_session(project, post, Provider.OPENROUTER), engine, monkeypatch)
    assert result["model"] == VideoModel.OR_SEEDANCE_2_0_MINI.value
    assert result["cost_usd"] == 0.1512


def test_the_saved_pick_is_the_model_unless_the_user_named_another(
    db, engine, project, post, uploads, fake_videos, monkeypatch,
):
    session = _session(project, post, Provider.OPENROUTER, model=VideoModel.OR_SEEDANCE_2_5.value)
    _generate(session, engine, monkeypatch)
    # A Veo id on an OpenRouter key means "a clip": it becomes that key's model.
    _generate(session, engine, monkeypatch, model=VideoModel.VEO_3_1.value)
    assert [c["request"].model for c in fake_videos.calls] == [
        VideoModel.OR_SEEDANCE_2_5, VideoModel.OR_SEEDANCE_2_0_MINI,
    ]


def test_a_first_frame_is_read_from_the_project_and_remembered_as_the_poster(
    db, engine, project, post, uploads, fake_videos, monkeypatch,
):
    (uploads / "kf.png").write_bytes(PNG)
    frame = _image_asset(db, project)
    result = _generate(_session(project, post), engine, monkeypatch, first_frame_asset_id=str(frame.id))

    (call,) = fake_videos.calls
    assert call["first_frame"].data == PNG and call["first_frame"].url == ""
    db.refresh(post)
    assert post.video["first_frame_url"] == "/uploads/kf.png"
    assert result["asset_id"] == post.video["asset_id"]


@pytest.mark.parametrize(
    "args",
    [
        {"last_frame_asset_id": str(uuid4())},                 # a last frame alone
        {"first_frame_asset_id": str(uuid4())},                # not this project's
        {"first_frame_asset_id": "not-an-id"},
    ],
)
def test_a_bad_frame_is_refused_before_anything_is_paid_for(
    db, engine, project, post, uploads, fake_videos, monkeypatch, args,
):
    result = _generate(_session(project, post), engine, monkeypatch, **args)
    assert result["status"] == "error"
    assert fake_videos.calls == []


def test_a_clip_is_not_an_image_frame(db, engine, project, post, uploads, fake_videos, monkeypatch):
    clip = ContentAsset(project_id=project.id, asset_type="generated", url="/uploads/c.mp4", mime_type="video/mp4")
    db.add(clip)
    db.commit()
    result = _generate(_session(project, post), engine, monkeypatch, first_frame_asset_id=str(clip.id))
    assert result["status"] == "error" and "image" in result["message"]


@pytest.mark.parametrize(
    ("code", "says"),
    [
        (VideoErrorCode.PERSON, "realistic person"),
        (VideoErrorCode.SAFETY, "safety filter"),
        (VideoErrorCode.BILLING, "out of credit"),
        (VideoErrorCode.TIMEOUT, "ten minutes"),
    ],
)
def test_a_failed_clip_says_what_to_change_and_saves_nothing(
    db, engine, project, post, uploads, monkeypatch, code, says,
):
    fake = FakeVideos(error=VideoAPIError("upstream", model="m", code=code))
    monkeypatch.setattr(videos, "video_client_for", fake.client_for)
    result = _generate(_session(project, post), engine, monkeypatch)
    assert result["status"] == "error" and says in result["message"]
    assert db.exec(select(ContentAsset).where(ContentAsset.post_id == post.id)).all() == []
    db.refresh(post)
    assert post.video is None and post.post_type == "slideshow"


# --- takes, the routes, publishing ------------------------------------------------


def _client(engine, user) -> TestClient:
    def fresh_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = fresh_session
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _two_takes(engine, project, post, monkeypatch) -> tuple[str, str]:
    session = _session(project, post)
    first = _generate(session, engine, monkeypatch)["asset_id"]
    second = _generate(session, engine, monkeypatch)["asset_id"]
    return first, second


def test_every_take_is_kept_and_a_member_can_choose_one(
    db, engine, owner, project, post, uploads, fake_videos, monkeypatch,
):
    first, second = _two_takes(engine, project, post, monkeypatch)
    client = _client(engine, owner)

    body = client.get(f"/api/content/posts/{post.id}").json()
    assert body["video"]["asset_id"] == second
    assert [t["asset_id"] for t in body["video_takes"]] == [second, first]
    assert [t["is_cut"] for t in body["video_takes"]] == [True, False]

    res = client.post(f"/api/content/posts/{post.id}/video/select", json={"asset_id": first})
    assert res.status_code == 200 and res.json()["video"]["asset_id"] == first


def test_a_take_is_chosen_only_from_this_post_by_a_member(
    db, engine, owner, project, post, uploads, fake_videos, monkeypatch,
):
    first, _second = _two_takes(engine, project, post, monkeypatch)
    stranger = _user(db, "video-stranger@example.com")
    assert _client(engine, stranger).post(
        f"/api/content/posts/{post.id}/video/select", json={"asset_id": first},
    ).status_code == 404

    other = ContentPost(project_id=project.id, post_dir_slug="other-day")
    db.add(other)
    db.commit()
    assert _client(engine, owner).post(
        f"/api/content/posts/{other.id}/video/select", json={"asset_id": first},
    ).status_code == 404


def test_a_clip_is_never_a_cards_thumbnail(db, engine, owner, project, post, uploads, fake_videos, monkeypatch):
    _generate(_session(project, post), engine, monkeypatch)
    (card,) = _client(engine, owner).get(
        "/api/content/posts", params={"project_id": str(project.id), "status": "pending"},
    ).json()
    assert card["thumbnail_url"] == "" and card["video"]["url"].endswith(".mp4")


class FakePostBridge:
    def __init__(self):
        self.uploads: list[tuple[str, str, int]] = []
        self.posts: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def create_upload_url(self, *, name, mime_type, size_bytes):
        self.uploads.append((name, mime_type, size_bytes))
        return SimpleNamespace(upload_url="https://upload.example/x", media_id=f"m{len(self.uploads)}")

    async def upload_media(self, data, url, content_type):
        return None

    async def create_post(self, request):
        self.posts.append(request)
        return SimpleNamespace(id="pb_1", status=SimpleNamespace(value="scheduled"), scheduled_at=None)


@pytest.fixture
def post_bridge_fake(monkeypatch):
    fake = FakePostBridge()
    monkeypatch.setattr(post_bridge, "client_for_user", lambda _uid, _db: fake)
    return fake


def test_publishing_a_video_post_sends_its_cut_and_nothing_else(
    db, engine, owner, project, post, uploads, fake_videos, monkeypatch, post_bridge_fake,
):
    (uploads / "kf.png").write_bytes(PNG)
    frame = _image_asset(db, project)
    frame.post_id = post.id
    db.add(frame)
    db.commit()
    _, cut = _two_takes(engine, project, post, monkeypatch)

    res = _client(engine, owner).post(
        f"/api/content/posts/{post.id}/publish", json={"social_account_ids": [7], "tiktok_draft": True},
    )
    assert res.status_code == 200, res.text
    ((name, mime, size),) = post_bridge_fake.uploads
    assert mime == "video/mp4" and name == f"{cut}.mp4" and size == len(CLIP)
    assert post_bridge_fake.posts[0].media == ["m1"]


def test_a_video_post_with_no_clip_is_not_published(db, engine, owner, project, post, post_bridge_fake):
    post.post_type = "video"
    db.add(post)
    db.commit()
    res = _client(engine, owner).post(f"/api/content/posts/{post.id}/publish", json={"social_account_ids": [7]})
    assert res.status_code == 400 and post_bridge_fake.uploads == []


def test_the_agents_publish_sends_the_cut_too(
    db, engine, project, post, uploads, fake_videos, monkeypatch, post_bridge_fake,
):
    session = _session(project, post)
    _generate(session, engine, monkeypatch)
    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, lambda e: asyncio.sleep(0), session)}
    result = json.loads(asyncio.run(tools["publish_post"].ainvoke({
        "post_id": str(post.id), "social_account_ids": [7],
    })))
    assert result["media_count"] == 1
    assert post_bridge_fake.uploads[0][1] == "video/mp4"


# --- which key pays, and what the settings page promises -----------------------


def _keys(monkeypatch, available: dict[Provider, str]):
    def resolve(provider, user_keys, *, stored_keys=None, plan_ok=True):
        if provider in available:
            return SimpleNamespace(key=available[provider], source="user")
        raise engines.ProviderKeyRequired(provider)

    monkeypatch.setattr(engines, "resolve_provider_key", resolve)


def test_video_goes_to_gemini_first_then_openrouter_then_nowhere(monkeypatch):
    _keys(monkeypatch, {Provider.GOOGLE_GENAI: "g", Provider.OPENROUTER: "o"})
    assert engines.resolve_video_run().model is VideoModel.VEO_3_1_LITE
    _keys(monkeypatch, {Provider.OPENROUTER: "o", Provider.OPENAI: "sk"})
    assert engines.resolve_video_run().model is VideoModel.OR_SEEDANCE_2_0_MINI
    _keys(monkeypatch, {Provider.OPENAI: "sk", Provider.ANTHROPIC: "ant"})
    assert engines.resolve_video_run() is None


def test_a_saved_pick_is_honoured_when_its_key_is_there_and_skipped_when_not(monkeypatch):
    _keys(monkeypatch, {Provider.GOOGLE_GENAI: "g", Provider.OPENROUTER: "o"})
    picked = engines.resolve_video_run(preferred=VideoModel.OR_SEEDANCE_2_5.value)
    assert (picked.provider, picked.model) == (Provider.OPENROUTER, VideoModel.OR_SEEDANCE_2_5)
    _keys(monkeypatch, {Provider.GOOGLE_GENAI: "g"})
    assert engines.resolve_video_run(preferred=VideoModel.OR_SEEDANCE_2_5.value).model is VideoModel.VEO_3_1_LITE


def test_the_session_holds_the_resolved_video_run(monkeypatch):
    session = make_session("video-sess", uuid4(), "draft_post")
    monkeypatch.setattr("agents.core.session.get_session", lambda _sid: session)
    monkeypatch.setattr(content_routes, "stored_keys_for", lambda _uid: {})
    _keys(monkeypatch, {Provider.OPENROUTER: "or-mine"})
    content_routes._attach_video_run("video-sess", {Provider.OPENROUTER: "or-mine"})
    assert (session.video_provider, session.video_api_key, session.video_model) == (
        Provider.OPENROUTER, "or-mine", VideoModel.OR_SEEDANCE_2_0_MINI.value,
    )


def test_the_videos_row_and_the_catalogue_come_from_the_same_tables():
    from agents.models import DEFAULT_VIDEO_MODELS, VIDEO_PROVIDER_ORDER
    from routes.providers import _media_status, models_catalogue

    row = _media_status({"openrouter": "stored"}, None, VIDEO_PROVIDER_ORDER, DEFAULT_VIDEO_MODELS)
    assert row == {"provider": "openrouter", "model": VideoModel.OR_SEEDANCE_2_0_MINI.value, "source": "stored"}
    catalogue = models_catalogue()
    assert {m["id"] for m in catalogue["video_models"]} == {m.value for m in VideoModel}
    assert catalogue["video_provider_order"] == ["google_genai", "openrouter"]


# --- the card and the guard -------------------------------------------------------


def test_the_video_card_carries_the_clip_and_what_it_cost():
    start, finish = ACTIVITY_TOOLS["generate_video"]
    assert start({"prompt": "a kettle"})["kind"] is ActivityKind.VIDEO
    done = finish({"prompt": "a kettle"}, json.dumps({
        "url": "/uploads/c.mp4", "model": "veo-3.1-lite-generate-preview", "duration_seconds": 8, "cost_usd": 0.4,
    }), False)
    assert done["status"] is StepStatus.SUCCESS
    assert done["meta"] == {
        "videos": ["/uploads/c.mp4"], "model": "veo-3.1-lite-generate-preview",
        "duration_seconds": 8, "cost_usd": 0.4,
    }
    failed = finish({"prompt": "a kettle"}, json.dumps({"status": "error", "message": "nope"}), False)
    assert failed["status"] is StepStatus.ERROR and failed["error"] == "nope"


def test_a_content_turn_makes_at_most_three_clips():
    from agents.content.v1.runner import LIMITS
    from agents.core.deep_session import session_middleware

    assert ("generate_video", 3) in LIMITS.per_tool_run_limits
    names = [getattr(m, "name", "") for m in session_middleware(LIMITS)]
    assert "ToolCallLimitMiddleware[generate_video]" in names
