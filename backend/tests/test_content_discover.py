"""Discover: saved references keep their pictures, repeat searches reuse runs.

Two promises from issue #225, each held end to end through the real routes:

* a saved reference copies its cover and slides into project storage, so it
  still has them after TikTok's signed URLs expire — and a copy that was lost
  or failed is picked up again by the backfill;
* the same search inside the reuse window starts no second Apify run.

Both vendors are faked at the transport (``httpx.MockTransport``), so the
requests asserted on are the ones that would have left the building.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import routes.content as content_routes
import service.apify.run_cache as run_cache
import service.auth as auth_service
import service.discovery as discovery
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentAsset
from models.membership import ProjectMember
from models.project import Project
from service import storage
from service.apify import ApifyClient
from service.apify.schema import ScrapedPost
from service.discovery import MAX_CAPTURE_ATTEMPTS, MediaStatus
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

COVER = "https://p16-sign-va.tiktokcdn.com/cover~tplv.jpeg?x-expires=1&x-signature=a"
SLIDE_1 = "https://p16-sign-va.tiktokcdn.com/s1~tplv-photomode.jpeg?x-expires=1"
SLIDE_2 = "https://p16-sign-va.tiktokcdn.com/s2~tplv-photomode.webp?x-expires=1"
JPEG = b"\xff\xd8\xff" + b"j" * 32
WEBP = b"RIFF" + b"w" * 32


def apify_item(**overrides) -> dict:
    """One dataset item, camelCase as the actor returns it."""
    item = {
        "id": "7300000000000000001",
        "text": "Three face shapes nobody talks about\n#faceshape",
        "webVideoUrl": "https://www.tiktok.com/@kestrel/video/7300000000000000001",
        "isSlideshow": True,
        "playCount": 120_000,
        "diggCount": 9_000,
        "collectCount": 2_400,
        "videoMeta": {"coverUrl": COVER},
        "slideshowImageLinks": [SLIDE_1, SLIDE_2],
        "hashtags": ["faceshape"],
    }
    item.update(overrides)
    return item


def as_the_browser_sends_it(item: dict) -> dict:
    """The results route dumps posts snake_case, and the browser saves that shape."""
    return ScrapedPost.model_validate(item).model_dump(mode="json")


class Cdn:
    """TikTok's image CDN: serves the known images, 403s once a URL "expires"."""

    def __init__(self):
        self.images = {COVER: (JPEG, "image/jpeg"), SLIDE_1: (JPEG, "image/jpeg"), SLIDE_2: (WEBP, "image/webp")}
        self.expired: set[str] = set()
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url in self.expired or url not in self.images:
            return httpx.Response(403, content=b"expired")
        body, content_type = self.images[url]
        return httpx.Response(200, content=body, headers={"content-type": content_type})


@pytest.fixture
def cdn(monkeypatch):
    fake = Cdn()
    monkeypatch.setattr(
        discovery, "_new_media_client", lambda: httpx.Client(transport=httpx.MockTransport(fake))
    )
    return fake


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage, "get_configs", lambda: cfg)
    return tmp_path


@pytest.fixture
def engine():
    return make_sqlite_engine()


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
    return _user(db, "discover-owner@example.com")


@pytest.fixture
def stranger(db):
    return _user(db, "discover-stranger@example.com")


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Kestrel Studio")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


def client(db, user):
    """A client whose every request gets its own session, as in production.

    Sharing the test's session would serve a request rows cached before a
    background task rewrote them, which no real request ever sees.
    """
    engine = db.get_bind()

    def fresh_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = fresh_session
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def save(c, project, item=None):
    return c.post("/api/content/discover/save", json={
        "project_id": str(project.id),
        "actor_id": "clockworks/tiktok-scraper",
        "run_id": "run1",
        "dataset_id": "ds1",
        "request": {"hashtags": ["faceshape"]},
        "post": as_the_browser_sends_it(item or apify_item()),
    })


def reload(db, asset_id) -> ContentAsset:
    db.expire_all()
    return db.get(ContentAsset, UUID(str(asset_id)))


# ---------------------------------------------------------------------------
# Saving keeps the post and its pictures
# ---------------------------------------------------------------------------

def test_a_saved_reference_keeps_the_whole_post(db, project, owner, cdn, uploads):
    """The round trip through the browser used to strip every aliased field."""
    res = save(client(db, owner), project)
    assert res.status_code == 201
    asset = reload(db, res.json()["id"])
    post = asset.params["post"]
    assert asset.url == "https://www.tiktok.com/@kestrel/video/7300000000000000001"
    assert post["play_count"] == 120_000
    assert post["slideshow_image_links"] == [SLIDE_1, SLIDE_2]
    assert post["video_meta"]["cover_url"] == COVER
    assert asset.params["run_id"] == "run1"


def test_a_saved_reference_copies_its_pictures_into_project_storage(db, project, owner, cdn, uploads):
    res = save(client(db, owner), project)
    asset = reload(db, res.json()["id"])
    media = asset.params["media"]

    assert media["status"] == MediaStatus.OK
    assert media["attempts"] == 1
    stem = f"/uploads/projects/{project.id}/discovered_reference/{asset.id}"
    assert media["cover"] == f"{stem}/cover.jpg"
    assert media["slides"] == [f"{stem}/slide-00.jpg", f"{stem}/slide-01.webp"]
    # The bytes are ours now: the reference no longer depends on TikTok's URLs.
    assert (uploads / Path(media["slides"][1]).relative_to("/uploads")).read_bytes() == WEBP


def test_the_pictures_outlive_the_tiktok_urls(db, project, owner, cdn, uploads):
    """Done-means for #225: a reference saved today still shows its images later."""
    res = save(client(db, owner), project)
    cdn.expired.update({COVER, SLIDE_1, SLIDE_2})

    media = reload(db, res.json()["id"]).params["media"]
    for url in [media["cover"], *media["slides"]]:
        assert storage.get_bytes(url) in (JPEG, WEBP)


def test_saving_the_same_post_again_updates_one_row(db, project, owner, cdn, uploads):
    c = client(db, owner)
    first = save(c, project).json()["id"]
    fetched_once = len(cdn.requests)
    second = save(c, project, apify_item(playCount=250_000)).json()["id"]

    assert first == second
    assert len(db.exec(select(ContentAsset)).all()) == 1
    asset = reload(db, first)
    assert asset.params["post"]["play_count"] == 250_000
    assert asset.params["media"]["status"] == MediaStatus.OK
    assert len(cdn.requests) == fetched_once, "a captured reference is not fetched again"


def test_a_video_reference_keeps_its_cover(db, project, owner, cdn, uploads):
    video = apify_item(isSlideshow=False, slideshowImageLinks=[])
    media = reload(db, save(client(db, owner), project, video).json()["id"]).params["media"]
    assert media["status"] == MediaStatus.OK
    assert media["cover"].endswith("/cover.jpg") and media["slides"] == []


def test_a_post_with_no_images_is_recorded_as_empty_and_left_alone(db, project, owner, cdn, uploads):
    bare = apify_item(videoMeta=None, slideshowImageLinks=[])
    asset = reload(db, save(client(db, owner), project, bare).json()["id"])
    assert asset.params["media"]["status"] == MediaStatus.EMPTY
    assert not discovery.needs_media(asset.params)


def test_an_image_url_off_the_allowlist_is_never_fetched(db, project, owner, cdn, uploads):
    """The post arrives from the browser, so its URLs are the caller's to choose."""
    hostile = apify_item(
        videoMeta={"coverUrl": "https://169.254.169.254/latest/meta-data/"},
        slideshowImageLinks=["https://evil.example/a.jpg", SLIDE_1],
    )
    asset = reload(db, save(client(db, owner), project, hostile).json()["id"])

    assert [str(r.url) for r in cdn.requests] == [SLIDE_1]
    assert asset.params["media"]["status"] == MediaStatus.PARTIAL
    assert len(asset.params["media"]["slides"]) == 1


def test_an_apify_record_gets_the_token_and_nothing_else_does(db, project, owner, cdn, uploads, monkeypatch):
    token = "apify-test-token"
    monkeypatch.setattr(discovery, "get_configs", lambda: Configs(apify_api_key=token))
    record = "https://api.apify.com/v2/key-value-stores/kv1/records/cover-7300"
    cdn.images[record] = (JPEG, "image/jpeg")

    save(client(db, owner), project, apify_item(videoMeta={"coverUrl": record}))

    sent = {str(r.url): r.headers.get("authorization") for r in cdn.requests}
    assert sent[record] == f"Bearer {token}"
    assert sent[SLIDE_1] is None and sent[SLIDE_2] is None


# ---------------------------------------------------------------------------
# The backfill
# ---------------------------------------------------------------------------

def _legacy_reference(db, project, item=None) -> ContentAsset:
    """A row saved before capture existed: a post, no media record."""
    asset = ContentAsset(
        project_id=project.id,
        asset_type=discovery.REFERENCE_ASSET_TYPE,
        source=discovery.REFERENCE_SOURCE,
        url="https://www.tiktok.com/@kestrel/video/1",
        filename="tiktok-legacy",
        params={"post": as_the_browser_sends_it(item or apify_item(id="legacy"))},
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def test_the_backfill_captures_references_saved_before(db, project, owner, cdn, uploads):
    legacy = _legacy_reference(db, project)
    res = client(db, owner).post("/api/content/discover/recapture", json={"project_id": str(project.id)})

    assert res.status_code == 202 and res.json() == {"queued": 1}
    assert reload(db, legacy.id).params["media"]["status"] == MediaStatus.OK


def test_the_backfill_retries_a_failure_up_to_the_ceiling(db, project, owner, cdn, uploads):
    legacy = _legacy_reference(db, project)
    cdn.expired.update({COVER, SLIDE_1, SLIDE_2})
    c = client(db, owner)

    queued = [
        c.post("/api/content/discover/recapture", json={"project_id": str(project.id)}).json()["queued"]
        for _ in range(MAX_CAPTURE_ATTEMPTS + 1)
    ]

    assert queued == [1] * MAX_CAPTURE_ATTEMPTS + [0]
    media = reload(db, legacy.id).params["media"]
    assert media["status"] == MediaStatus.FAILED and media["attempts"] == MAX_CAPTURE_ATTEMPTS


def test_resaving_a_failed_reference_earns_fresh_attempts(db, project, owner, cdn, uploads):
    """A new save brings newly signed URLs, so the old failures stop counting."""
    c = client(db, owner)
    cdn.expired.update({COVER, SLIDE_1, SLIDE_2})
    asset_id = save(c, project).json()["id"]
    assert reload(db, asset_id).params["media"]["status"] == MediaStatus.FAILED

    cdn.expired.clear()
    save(c, project)
    media = reload(db, asset_id).params["media"]
    assert media["status"] == MediaStatus.OK and media["attempts"] == 1


def test_a_deleted_reference_is_skipped_quietly(db, project, cdn, uploads, engine):
    legacy = _legacy_reference(db, project)
    db.delete(legacy)
    db.commit()
    assert discovery.capture_reference_media(legacy.id, open_db=lambda: Session(engine)) is None


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/content/discover/save", "/api/content/discover/recapture"])
def test_a_stranger_cannot_save_or_backfill_into_another_project(db, project, stranger, cdn, uploads, path):
    _legacy_reference(db, project)
    body = {"project_id": str(project.id)}
    if path.endswith("/save"):
        body.update(actor_id="a", run_id="r", dataset_id="d", post=as_the_browser_sends_it(apify_item()))

    res = client(db, stranger).post(path, json=body)

    assert res.status_code == 404
    assert cdn.requests == [], "nothing is fetched on a stranger's say-so"
    assert len(db.exec(select(ContentAsset)).all()) == 1


# ---------------------------------------------------------------------------
# Repeat searches reuse the Apify run
# ---------------------------------------------------------------------------

class Apify:
    """Apify's run endpoints: counts starts, reports whatever status is set."""

    def __init__(self):
        self.starts = 0
        self.status = "RUNNING"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/runs"):
            self.starts += 1
            run_id = f"run{self.starts}"
            return httpx.Response(201, json={"data": {"id": run_id, "status": "READY", "defaultDatasetId": f"ds-{run_id}"}})
        run_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={"data": {"id": run_id, "status": self.status, "defaultDatasetId": f"ds-{run_id}"}})

    def client(self) -> ApifyClient:
        return ApifyClient("apify-test-key", client=httpx.AsyncClient(transport=httpx.MockTransport(self)))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def apify(monkeypatch):
    fake = Apify()
    monkeypatch.setattr(content_routes, "_apify_client_or_503", fake.client)
    return fake


@pytest.fixture
def clock(monkeypatch):
    tick = Clock()
    monkeypatch.setattr(run_cache, "apify_runs", run_cache.RunCache(clock=tick))
    return tick


def start(c, project, payload=None, actor="clockworks/tiktok-scraper"):
    return c.post("/api/content/discover/start", json={
        "project_id": str(project.id),
        "actor_id": actor,
        "input_payload": payload if payload is not None else {"hashtags": ["faceshape"], "resultsPerPage": 30},
    })


def test_repeating_a_search_starts_no_new_run(db, project, owner, apify, clock):
    c = client(db, owner)
    first = start(c, project).json()
    apify.status = "SUCCEEDED"
    clock.now += run_cache.RUN_REUSE_TTL_SECONDS - 1
    second = start(c, project, {"resultsPerPage": 30, "hashtags": ["faceshape"]}).json()

    assert apify.starts == 1
    assert second["run_id"] == first["run_id"] and second["dataset_id"] == first["dataset_id"]
    assert second["status"] == "SUCCEEDED"


def test_a_different_search_is_a_different_run(db, project, owner, apify, clock):
    c = client(db, owner)
    start(c, project)
    start(c, project, {"hashtags": ["colorseason"], "resultsPerPage": 30})
    start(c, project, actor="clockworks/free-tiktok-scraper")
    assert apify.starts == 3


def test_the_same_search_after_the_window_runs_again(db, project, owner, apify, clock):
    c = client(db, owner)
    start(c, project)
    clock.now += run_cache.RUN_REUSE_TTL_SECONDS
    start(c, project)
    assert apify.starts == 2


def test_a_failed_run_is_not_reused(db, project, owner, apify, clock):
    c = client(db, owner)
    start(c, project)
    apify.status = "FAILED"
    assert start(c, project).json()["run_id"] == "run2"


def test_the_store_and_api_spellings_of_an_actor_share_a_run():
    assert run_cache.run_key("clockworks/tiktok-scraper", {"b": 1, "a": 2}) == run_cache.run_key(
        "clockworks~tiktok-scraper", {"a": 2, "b": 1}
    )


def test_the_cache_forgets_the_oldest_run_past_its_cap():
    apify = Apify()
    cache = run_cache.RunCache(max_entries=2, clock=Clock())

    async def run_all():
        async with apify.client() as c:
            for tag in ("a", "b", "c", "a"):
                await cache.start(c, "actor", {"hashtags": [tag]})

    asyncio.run(run_all())
    assert apify.starts == 4  # "a" was evicted by "c", so its repeat ran again
