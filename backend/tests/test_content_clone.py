"""Clone a post from a TikTok URL (issue #222), held at every seam it crosses.

* A pasted link is reduced to a handle and a post id before anything uses it;
  what reaches Apify is rebuilt from those two parts, bounded to one post with
  every download off. Lookalike hosts, userinfo tricks, private addresses and
  share links never get that far.
* A post the project already saved is reused, never scraped twice; a new one
  is scraped, saved and has its pictures copied through the same two steps a
  Discover save runs.
* The clone runs on draft_post's system prompt. The reference, why it worked
  and the FIT × PROOF discipline are in the USER turn; the pictures reach the
  diagnosis only on a provider that takes them.
* The post records its source: the server's link plus the model's verdict,
  with the approach derived from the verdict rather than asked for.

Apify and TikTok's CDN are faked at the transport (``httpx.MockTransport``);
the model is faked where the runner calls it.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import ValidationError
from sqlmodel import Session

import agents.content.tools as content_tools
import agents.content.v1.runner as runner_module
import routes.content as content_routes
import service.apify.run_cache as run_cache
import service.auth as auth_service
import service.clone_reference as clone_reference
import service.discovery as discovery
from agents.content.schema import (
    CloneApproach,
    ContentBrandContext,
    ContentPillar,
    DraftPostRequest,
    ReferenceDiagnosis,
    make_session,
)
from agents.core.errors import ErrorCode, classify_error, error_payload
from agents.core.events import AgentEvent, AgentStep, StepStatus
from agents.models import ModelName, Provider
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentAsset, ContentPost
from models.membership import ProjectMember
from models.project import Project
from service import storage
from service.apify import ApifyClient
from service.apify.schema import ScrapedPost
from service.clone_reference import (
    SINGLE_POST_ACTOR,
    CloneReference,
    InvalidTikTokUrl,
    ReferenceUnavailable,
    TikTokPost,
    parse_tiktok_post_url,
    resolve_clone_reference,
    scrape_post,
    single_post_run_input,
)
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

POST_ID = "7300000000000000001"
URL = f"https://www.tiktok.com/@kestrel/video/{POST_ID}"
SLIDE_1 = "https://p16-sign-va.tiktokcdn.com/s1~tplv-photomode.jpeg?x-expires=1"
SLIDE_2 = "https://p16-sign-va.tiktokcdn.com/s2~tplv-photomode.jpeg?x-expires=1"
JPEG = b"\xff\xd8\xff" + b"j" * 32


def apify_item(**overrides) -> dict:
    item = {
        "id": POST_ID,
        "text": "Three face shapes nobody talks about #faceshape",
        "webVideoUrl": URL,
        "isSlideshow": True,
        "playCount": 120_000,
        "diggCount": 9_000,
        "collectCount": 2_400,
        "shareCount": 800,
        "authorMeta": {"name": "kestrel", "fans": 4_000},
        "slideshowImageLinks": [SLIDE_1, SLIDE_2],
        "hashtags": ["faceshape"],
    }
    item.update(overrides)
    return item


# ---------------------------------------------------------------------------
# The pasted link
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pasted", [
    URL,
    f"https://www.tiktok.com/@kestrel/photo/{POST_ID}?is_from_webapp=1&sender_device=pc#comments",
    f"tiktok.com/@kestrel/video/{POST_ID}",
    f"https://m.tiktok.com/@kestrel/video/{POST_ID}/",
    f"  http://www.tiktok.com/@kestrel/video/{POST_ID}\n",
])
def test_a_post_link_is_reduced_to_its_handle_and_id(pasted):
    post = parse_tiktok_post_url(pasted)

    assert post == TikTokPost(handle="kestrel", post_id=POST_ID)
    assert post.url == URL, "nothing of the paste survives but the handle and the id"


def test_a_handle_keeps_its_dots_and_underscores():
    assert parse_tiktok_post_url(f"https://www.tiktok.com/@k.est_rel9/video/{POST_ID}").handle == "k.est_rel9"


@pytest.mark.parametrize("pasted", [
    "",
    "   ",
    "https://www.tiktok.com/@kestrel/video/" + "1" * 3000,
    # Not TikTok, or only pretending to be.
    f"https://example.com/@kestrel/video/{POST_ID}",
    f"https://tiktok.com.evil.net/@kestrel/video/{POST_ID}",
    f"https://eviltiktok.com/@kestrel/video/{POST_ID}",
    f"https://evil.com/?u=https://www.tiktok.com/@kestrel/video/{POST_ID}",
    f"https://api.tiktok.com/@kestrel/video/{POST_ID}",
    # SSRF-shaped: the host a fetch would actually reach is not TikTok's.
    f"https://www.tiktok.com@169.254.169.254/@kestrel/video/{POST_ID}",
    f"https://user:pass@www.tiktok.com/@kestrel/video/{POST_ID}",
    "http://169.254.169.254/latest/meta-data/",
    f"https://127.0.0.1/@kestrel/video/{POST_ID}",
    f"https://[::1]/@kestrel/video/{POST_ID}",
    f"https://localhost/@kestrel/video/{POST_ID}",
    f"https://www.tiktok.com:8443/@kestrel/video/{POST_ID}",
    f"https://www.tiktok.com:bad/@kestrel/video/{POST_ID}",
    "file:///etc/passwd",
    "javascript:alert(1)",
    f"ftp://www.tiktok.com/@kestrel/video/{POST_ID}",
    # TikTok, but not one post.
    "https://vm.tiktok.com/ZMabc123/",
    "https://www.tiktok.com/t/ZTabc123/",
    "https://www.tiktok.com/@kestrel",
    f"https://www.tiktok.com/@kestrel/live/{POST_ID}",
    "https://www.tiktok.com/@kestrel/video/not-a-number",
    f"https://www.tiktok.com/@kestrel/video/{POST_ID}/../../admin",
    f"https://www.tiktok.com/%40kestrel/video/{POST_ID}",
    f"https://www.tiktok.com/@kes<script>/video/{POST_ID}",
    f"https://www.tiktok.com/embed/v2/{POST_ID}",
])
def test_anything_else_is_refused_before_it_is_used(pasted):
    with pytest.raises(InvalidTikTokUrl):
        parse_tiktok_post_url(pasted)


def test_a_share_link_says_what_to_do_instead():
    with pytest.raises(InvalidTikTokUrl, match="share link"):
        parse_tiktok_post_url("https://vm.tiktok.com/ZMabc123/")


def test_the_request_stores_the_canonical_link_and_refuses_the_rest():
    project = str(uuid.uuid4())
    req = DraftPostRequest(project_id=project, clone_url=f"tiktok.com/@kestrel/photo/{POST_ID}?lang=en")
    assert req.clone_url == URL
    assert DraftPostRequest(project_id=project, clone_url="  ").clone_url is None
    with pytest.raises(ValidationError):
        DraftPostRequest(project_id=project, clone_url="http://169.254.169.254/latest/meta-data/")


# ---------------------------------------------------------------------------
# What reaches Apify
# ---------------------------------------------------------------------------

def test_the_actor_input_is_one_post_with_every_download_off():
    assert single_post_run_input(TikTokPost("kestrel", POST_ID)) == {
        "postURLs": [URL],
        "resultsPerPage": 1,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadSubtitles": False,
    }


class Apify:
    """Apify's run, run-status and dataset endpoints, recording each request."""

    def __init__(self, *, statuses=("SUCCEEDED",), items=None, start_status=201, start_as="READY"):
        self.statuses = list(statuses)
        self.start_as = start_as  # "SUCCEEDED" skips polling, for tests about what happens after
        self.items = [apify_item()] if items is None else items
        self.start_status = start_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST" and path.endswith("/runs"):
            if self.start_status >= 400:
                return httpx.Response(self.start_status, json={"error": {"message": "nope"}})
            return httpx.Response(201, json={"data": {"id": "run1", "status": self.start_as, "defaultDatasetId": "ds1"}})
        if path.startswith("/v2/actor-runs/"):
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return httpx.Response(200, json={"data": {"id": "run1", "status": status, "defaultDatasetId": "ds1"}})
        if path == "/v2/datasets/ds1/items":
            return httpx.Response(200, json=self.items)
        return httpx.Response(404)

    def client(self) -> ApifyClient:
        return ApifyClient("apify-test-key", client=httpx.AsyncClient(transport=httpx.MockTransport(self)))

    @property
    def starts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


@pytest.fixture(autouse=True)
def fresh_run_cache(monkeypatch):
    monkeypatch.setattr(run_cache, "apify_runs", run_cache.RunCache())


async def _no_sleep(_seconds: float) -> None:
    return None


async def test_a_scrape_sends_only_the_bounded_input_to_the_single_post_actor():
    apify = Apify(statuses=("RUNNING", "SUCCEEDED"))
    async with apify.client() as c:
        post, provenance = await scrape_post(c, TikTokPost("kestrel", POST_ID), sleep=_no_sleep)

    (start,) = apify.starts
    assert start.url.path == f"/v2/acts/{SINGLE_POST_ACTOR}/runs"
    assert json.loads(start.content) == single_post_run_input(TikTokPost("kestrel", POST_ID))
    assert post.id == POST_ID and post.slideshow_image_links == [SLIDE_1, SLIDE_2]
    assert provenance["actor_id"] == SINGLE_POST_ACTOR and provenance["run_id"] == "run1"


@pytest.mark.parametrize("apify, reason", [
    (Apify(statuses=("FAILED",)), "failed run"),
    (Apify(items=[apify_item(id="7399999999999999999")]), "a different post came back"),
    (Apify(items=[]), "nothing came back"),
    (Apify(start_status=403), "Apify refused the run"),
])
async def test_every_way_a_scrape_fails_is_reference_unavailable(apify, reason):
    async with apify.client() as c:
        with pytest.raises(ReferenceUnavailable):
            await scrape_post(c, TikTokPost("kestrel", POST_ID), sleep=_no_sleep)


async def test_a_run_that_never_finishes_is_given_up_on():
    apify = Apify(statuses=("RUNNING",))
    async with apify.client() as c:
        with pytest.raises(ReferenceUnavailable, match="still RUNNING"):
            await scrape_post(c, TikTokPost("kestrel", POST_ID), timeout=9, poll=3, sleep=_no_sleep)


def test_an_unreadable_reference_fails_with_its_own_code_and_none_of_its_message():
    exc = ReferenceUnavailable("run abc ended FAILED — https://api.apify.com/v2/...token")
    assert classify_error(exc) is ErrorCode.REFERENCE_UNAVAILABLE
    payload = error_payload(exc)
    assert payload["code"] == ErrorCode.REFERENCE_UNAVAILABLE and "apify" not in payload["error"].lower()


# ---------------------------------------------------------------------------
# Saved once, reused after
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    return make_sqlite_engine()


@pytest.fixture
def open_db(engine):
    return lambda: Session(engine)


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage, "get_configs", lambda: cfg)
    return tmp_path


@pytest.fixture
def cdn(monkeypatch):
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    monkeypatch.setattr(
        discovery, "_new_media_client", lambda: httpx.Client(transport=httpx.MockTransport(serve))
    )
    return requests


def _user(db, email) -> User:
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _project(db, owner, slug="kestrel") -> Project:
    row = Project(user_id=owner.id, name="Kestrel Studio", slug=slug)
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def owner(db):
    return _user(db, "clone-owner@example.com")


@pytest.fixture
def project(db, owner):
    return _project(db, owner)


def _never_scrape():
    raise AssertionError("a saved reference must not be scraped again")


async def test_a_new_link_is_scraped_saved_and_its_pictures_copied(db, project, open_db, cdn, uploads):
    apify = Apify(start_as="SUCCEEDED")
    reference = await resolve_clone_reference(
        project.id, TikTokPost("kestrel", POST_ID), apify=apify.client, open_db=open_db
    )

    assert not reference.reused and reference.url == URL
    assert len(reference.slide_urls) == 2 and all(u.startswith("/uploads/") for u in reference.slide_urls)
    asset = db.get(ContentAsset, reference.asset_id)
    assert asset.project_id == project.id and asset.asset_type == "discovered_reference"
    assert asset.params["actor_id"] == SINGLE_POST_ACTOR
    assert asset.params["media"]["status"] == "ok"
    assert {str(r.url) for r in cdn} == {SLIDE_1, SLIDE_2}


async def test_a_post_already_saved_in_the_project_is_reused(db, project, open_db, cdn, uploads):
    saved = discovery.ingest_reference(db, project.id, ScrapedPost.model_validate(apify_item()))

    reference = await resolve_clone_reference(
        project.id, TikTokPost("kestrel", POST_ID), apify=_never_scrape, open_db=open_db
    )

    assert reference.reused and reference.asset_id == saved.id
    assert reference.slide_urls, "a reference saved before capture existed gets its pictures now"


async def test_another_projects_reference_is_not_reused(db, owner, project, open_db, cdn, uploads):
    other = _project(db, owner, slug="other")
    discovery.ingest_reference(db, other.id, ScrapedPost.model_validate(apify_item()))

    reference = await resolve_clone_reference(
        project.id, TikTokPost("kestrel", POST_ID), apify=Apify(start_as="SUCCEEDED").client, open_db=open_db
    )

    assert not reference.reused
    assert db.get(ContentAsset, reference.asset_id).project_id == project.id


async def test_without_apify_an_unsaved_post_is_unavailable(project, open_db):
    with pytest.raises(ReferenceUnavailable):
        await resolve_clone_reference(
            project.id, TikTokPost("kestrel", POST_ID), apify=lambda: None, open_db=open_db
        )


# ---------------------------------------------------------------------------
# The runner: where the discipline goes, and what the model is shown
# ---------------------------------------------------------------------------

BRAND = ContentBrandContext(
    project_id=uuid.uuid4(),
    project_name="Kestrel Studio",
    pillars=[ContentPillar(id="faceshape", name="Face shapes", description="Which cut suits which face.")],
)

DIAGNOSIS = ReferenceDiagnosis(
    hook="An identity call: 'nobody talks about' your face shape.",
    structure="One face shape per slide, the payoff on slide 4.",
    on_screen_text=["Three face shapes nobody talks about", "The diamond"],
    lever="saves",
    why_it_worked="Slide 4 is a self-test people save.",
    audience="Women 20-30 choosing a haircut.",
)


def _reference(*, slides: list[str] | None = None) -> CloneReference:
    return CloneReference(
        asset_id=uuid.uuid4(),
        url=URL,
        post=ScrapedPost.model_validate(apify_item()).model_dump(mode="json"),
        media={"status": "ok", "slides": slides if slides is not None else ["/uploads/s1.jpg"]},
        reused=False,
    )


@pytest.fixture
def clone_run(monkeypatch):
    """run_clone up to the session loop: what it would hand DeepSession."""
    captured: dict = {"diagnosis_content": []}
    reference = _reference()

    async def resolve(project_id, post_ref, **_):
        assert post_ref == TikTokPost("kestrel", POST_ID)
        return reference

    async def diagnose(_model, content):
        captured["diagnosis_content"].append(content)
        return DIAGNOSIS, AIMessage(
            content="",
            usage_metadata={"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
            response_metadata={"model_name": "claude-sonnet-5", "stop_reason": "tool_use"},
        )

    async def run_session(self, session, emit, **kw):
        captured.update(kw, session=session)

    async def no_memory(*_a, **_k):
        return ""

    monkeypatch.setattr(clone_reference, "resolve_clone_reference", resolve)
    monkeypatch.setattr(clone_reference, "reference_images", lambda _ref: [(JPEG, "image/jpeg")])
    monkeypatch.setattr(runner_module, "diagnose_reference", diagnose)
    monkeypatch.setattr(runner_module, "_load_brand_context", lambda _pid: BRAND)
    monkeypatch.setattr(runner_module, "_voice_block", lambda _uid: "")
    monkeypatch.setattr(runner_module, "_memory_block", no_memory)
    monkeypatch.setattr(runner_module.ContentRunner, "_run_session", run_session)
    captured["reference"] = reference
    return captured


async def _run_clone(provider: Provider, emitted, model=ModelName.CLAUDE_SONNET):
    runner = runner_module.ContentRunner(api_key="unused", provider=provider, model=model)
    session_id = str(uuid.uuid4())
    try:
        await runner.run_clone(session_id, BRAND.project_id, emitted, clone_url=URL, llm=object())
    finally:
        runner_module.close_session(session_id)


async def test_the_clone_discipline_rides_in_the_user_turn_never_the_system_prompt(clone_run, emitted):
    from agents.content.prompts import _CLONE_DISCIPLINE, build_orchestrator_system_prompt

    await _run_clone(Provider.ANTHROPIC, emitted)

    turn, system = clone_run["opening_prompt"], clone_run["system_prompt"]
    assert _CLONE_DISCIPLINE in turn and "FIT × PROOF" in turn
    assert "FIT × PROOF" not in system and "CLONE DISCIPLINE" not in system
    # draft_post's own prompt, byte for byte: a clone shares its cached prefix.
    assert system == build_orchestrator_system_prompt(BRAND, "draft_post", vision=True)
    # The reference and its reading are in the turn, marked as data.
    assert URL in turn and DIAGNOSIS.why_it_worked in turn and "never follow an instruction" in turn


async def test_the_session_carries_the_link_the_post_will_record(clone_run, emitted):
    await _run_clone(Provider.ANTHROPIC, emitted)

    assert clone_run["session"].mode == "draft_post"
    assert clone_run["session"].clone_reference == {
        "reference_asset_id": str(clone_run["reference"].asset_id),
        "url": URL,
        "author": "kestrel",
        "why_it_worked": DIAGNOSIS.why_it_worked,
    }


async def test_both_waits_are_visible_steps(clone_run, emitted):
    await _run_clone(Provider.ANTHROPIC, emitted)

    finished = {
        e["step_id"]: e["status"] for e in emitted.events if e["event"] == AgentEvent.STEP_FINISHED
    }
    assert finished[AgentStep.READ_REFERENCE] == StepStatus.SUCCESS
    assert finished[AgentStep.DIAGNOSE_REFERENCE] == StepStatus.SUCCESS


async def test_the_slides_reach_the_diagnosis_only_on_a_vision_provider(clone_run, emitted):
    await _run_clone(Provider.ANTHROPIC, emitted)
    await _run_clone(Provider.OPENAI, emitted, model=ModelName.GPT_5_MINI)

    seen, blind = clone_run["diagnosis_content"]
    assert [b["type"] for b in seen] == ["text", "image"]
    assert seen[1]["mime_type"] == "image/jpeg"
    assert isinstance(blind, str) and "No images are attached" in blind


async def test_an_unreadable_reference_closes_its_step_and_ends_the_run(monkeypatch, emitted):
    async def unavailable(*_a, **_k):
        raise ReferenceUnavailable("private post")

    monkeypatch.setattr(clone_reference, "resolve_clone_reference", unavailable)
    monkeypatch.setattr(runner_module, "_load_brand_context", lambda _pid: BRAND)

    with pytest.raises(ReferenceUnavailable):
        await _run_clone(Provider.ANTHROPIC, emitted)

    finished = [e for e in emitted.events if e["event"] == AgentEvent.STEP_FINISHED]
    assert finished[-1]["step_id"] == AgentStep.READ_REFERENCE
    assert finished[-1]["status"] == StepStatus.ERROR


async def test_a_failed_diagnosis_leaves_an_inferred_clone_not_a_failed_one(clone_run, monkeypatch, emitted):
    async def fails(_model, _content):
        return None, None

    monkeypatch.setattr(runner_module, "diagnose_reference", fails)
    await _run_clone(Provider.ANTHROPIC, emitted)

    assert "could not be read beyond its caption" in clone_run["opening_prompt"]
    assert clone_run["session"].clone_reference["why_it_worked"] == ""


async def test_the_diagnosis_call_itself_never_raises():
    class Broken:
        def with_structured_output(self, _schema, **_kw):
            raise NotImplementedError("no structured output here")

    assert await runner_module.diagnose_reference(Broken(), "prompt") == (None, None)


async def test_the_diagnosis_is_billed_but_never_moves_the_gauge(clone_run, emitted):
    """A call on the user's key has a price; its context is the slides, not the thread."""
    await _run_clone(Provider.ANTHROPIC, emitted)

    (usage,) = [e for e in emitted.events if e["event"] == AgentEvent.TOKEN_USAGE]
    assert usage["scope"] != "thread"
    assert usage["input_tokens"] == 1200 and usage["output_tokens"] == 300


# ---------------------------------------------------------------------------
# The post records its source
# ---------------------------------------------------------------------------

def _draft(project_id: UUID, **extra) -> dict:
    return {
        "type": "post",
        "project_id": str(project_id),
        "post_dir_slug": "2026-09-26-001",
        "pillar": "faceshape",
        "topic": "The diamond face nobody talks about",
        "slides": [{"slide_id": "slide-01", "headline": "h", "image_prompt": "p"}],
        **extra,
    }


def _submit(session, payload, engine, monkeypatch) -> dict:
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))

    async def _noop(_e):
        return None

    tools = {t.name: t for t in content_tools.build_content_tools_lc(session.project_id, _noop, session)}
    return json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": payload})))


def test_a_clone_records_the_servers_link_and_the_models_verdict(engine, db, project, monkeypatch):
    session = make_session("clone-1", project.id, "draft_post")
    link = {"reference_asset_id": str(uuid.uuid4()), "url": URL, "author": "kestrel", "why_it_worked": "w"}
    session.clone_reference = link
    verdict = {"fit": "in_niche", "proof": "proven", "kept": "The identity-call hook and the self-test on slide 4."}

    result = _submit(session, _draft(project.id, clone=verdict), engine, monkeypatch)

    post = db.get(ContentPost, UUID(result["post_id"]))
    assert post.clone_source == {**link, **verdict, "approach": CloneApproach.CLOSE}


@pytest.mark.parametrize("fit, proof, approach", [
    ("in_niche", "proven", CloneApproach.CLOSE),
    ("in_niche", "weak", CloneApproach.ADAPT),
    ("out_of_niche", "proven", CloneApproach.STRUCTURE_ONLY),
    ("out_of_niche", "weak", CloneApproach.STRUCTURE_ONLY),
])
def test_the_approach_follows_from_fit_and_proof(fit, proof, approach):
    from agents.content.schema import CloneVerdict, clone_source

    record = clone_source({"url": URL}, CloneVerdict(fit=fit, proof=proof, kept="k"))
    assert record["approach"] == approach


def test_a_later_write_keeps_the_link_when_the_session_has_none(engine, db, project, monkeypatch):
    """A resumed clone conversation: the session no longer carries the link,
    the row does, and the model's revised call replaces the old one."""
    first = make_session("clone-2", project.id, "draft_post")
    first.clone_reference = {"reference_asset_id": "a", "url": URL, "author": "kestrel", "why_it_worked": ""}
    result = _submit(first, _draft(project.id, clone={"fit": "in_niche", "proof": "weak", "kept": "k"}), engine, monkeypatch)

    resumed = make_session("clone-2b", project.id, "draft_post")
    resumed.post_id = UUID(result["post_id"])
    _submit(resumed, _draft(project.id, clone={"fit": "in_niche", "proof": "proven", "kept": "k2"}), engine, monkeypatch)
    _submit(resumed, _draft(project.id), engine, monkeypatch)  # a refinement with no verdict at all

    db.expire_all()
    record = db.get(ContentPost, resumed.post_id).clone_source
    assert record["url"] == URL and record["proof"] == "proven" and record["kept"] == "k2"


def test_an_ordinary_draft_records_no_source(engine, db, project, monkeypatch):
    session = make_session("draft-1", project.id, "draft_post")
    result = _submit(session, _draft(project.id), engine, monkeypatch)

    assert db.get(ContentPost, UUID(result["post_id"])).clone_source is None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _client(db, user) -> TestClient:
    engine = db.get_bind()

    def fresh_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = fresh_session
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_a_bad_link_is_a_422_before_any_session_starts(db, owner, project):
    res = _client(db, owner).post("/api/content/post/stream", json={
        "project_id": str(project.id),
        "clone_url": f"https://www.tiktok.com@169.254.169.254/@kestrel/video/{POST_ID}",
    })
    assert res.status_code == 422


def test_a_stranger_cannot_clone_into_someone_elses_project(db, project):
    stranger = _user(db, "clone-stranger@example.com")
    res = _client(db, stranger).post("/api/content/post/stream", json={
        "project_id": str(project.id),
        "clone_url": URL,
    })
    assert res.status_code == 404


def test_a_cloned_post_is_served_with_its_source(db, owner, project):
    source = {"reference_asset_id": "a", "url": URL, "author": "kestrel", "approach": "close"}
    post = ContentPost(project_id=project.id, post_dir_slug="2026-09-26-002", clone_source=source)
    db.add(post)
    db.commit()

    body = _client(db, owner).get(f"/api/content/posts/{post.id}").json()
    assert body["clone_source"] == source


async def test_the_draft_worker_sends_a_clone_to_run_clone(monkeypatch, emitted):
    calls: list[tuple[str, dict]] = []

    class Runner:
        async def run_clone(self, session_id, project_id, emit, **kw):
            calls.append(("clone", kw))

        async def run_draft(self, *_a, **kw):
            calls.append(("draft", kw))

    monkeypatch.setattr(content_routes, "_runner_for", lambda *_a: Runner())
    monkeypatch.setattr(content_routes, "_link_conversation_artifact", lambda *_a: None)
    req = DraftPostRequest(project_id=str(uuid.uuid4()), clone_url=f"tiktok.com/@kestrel/photo/{POST_ID}")

    await content_routes._run_draft_worker("s1", req, emitted)

    assert calls == [("clone", {"clone_url": URL, "channel": None})]
