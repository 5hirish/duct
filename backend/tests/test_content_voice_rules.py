"""A project's own voice for text posts (issue #271): writing samples the
writer matches, and the rules it keeps as settings.

What these pin:

  * the rules every project had as constants are the defaults, so a project
    that never edits them drafts exactly as before;
  * the project's values ride in the USER turn, never the cached system prompt;
  * the text writer refuses a banned word the way it refuses an over-length
    post, naming the word, and reads the rule fresh;
  * the Brand tab's caps hold at the route too.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import agents.content.tools as content_tools
import routes.content as content_routes
import service.auth as auth_service
from agents.content.channels import resolve
from agents.content.prompts import build_orchestrator_system_prompt, build_post_user_prompt
from agents.content.schema import ContentBrandContext
from agents.content.v1.runner import make_session
from agents.content.voice_rules import (
    DEFAULT_BANNED_WORDS,
    MAX_SAMPLES,
    RULES_KEY,
    SAMPLES_KEY,
    VoiceRules,
    banned_words_in,
    voice_rules_of,
    writing_samples_of,
)
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentPost
from models.membership import ProjectMember
from models.project import Project
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

SAMPLE = "We shipped the eval gate on a Tuesday.\n\nIt failed us twice before it caught the bug it was built for."


# ---------------------------------------------------------------------------
# The rules as settings
# ---------------------------------------------------------------------------


def test_a_project_that_never_set_them_runs_on_the_old_constants():
    rules = voice_rules_of({"tone": "dry"})

    assert rules.banned_words == list(DEFAULT_BANNED_WORDS)
    assert rules.no_client_names and rules.protect_the_edge


def test_an_empty_banned_list_is_a_choice_and_a_broken_row_is_the_default():
    assert voice_rules_of({RULES_KEY: {"banned_words": []}}).banned_words == []
    assert voice_rules_of({RULES_KEY: "nonsense"}) == VoiceRules()
    assert voice_rules_of({RULES_KEY: {"banned_words": ["  hot   take ", "Hot take", 7]}}).banned_words == ["hot take"]


def test_samples_drop_blanks_and_keep_to_the_cap():
    samples = writing_samples_of({SAMPLES_KEY: ["  ", SAMPLE, *[f"post {i}" for i in range(9)]]})

    assert samples[0] == SAMPLE and len(samples) == MAX_SAMPLES


def test_a_banned_phrase_is_matched_whole_and_case_blind():
    words = ["dive in", "here's a thread", "Game-changer"]

    assert banned_words_in("Let's DIVE   in.", words) == ["dive in"]
    assert banned_words_in("Here’s a thread on pricing", words) == ["here's a thread"]
    assert banned_words_in("a real game-changer", words) == ["Game-changer"]
    assert banned_words_in("We dive into the numbers.", words) == []


# ---------------------------------------------------------------------------
# Where they reach the model
# ---------------------------------------------------------------------------


def _brand(**content_brand) -> ContentBrandContext:
    return ContentBrandContext(
        project_id=uuid4(), project_name="Kestrel",
        writing_samples=writing_samples_of(content_brand), voice_rules=voice_rules_of(content_brand),
    )


def test_the_default_text_turn_carries_every_rule_the_system_prompt_used_to():
    turn = build_post_user_prompt(_brand(), None, topic="eval", pillar="build", channel=resolve("twitter"))

    for word in DEFAULT_BANNED_WORDS:
        assert f'"{word}"' in turn
    assert "Never name a customer, client or partner" in turn and "Protect the edge" in turn


def test_the_projects_voice_rides_in_the_user_turn_not_the_cached_prefix():
    brand = _brand(**{
        SAMPLES_KEY: [SAMPLE],
        RULES_KEY: {"banned_words": ["synergy"], "no_client_names": False, "protect_the_edge": False},
    })
    channel = resolve("linkedin")

    turn = build_post_user_prompt(brand, None, topic="eval", pillar="build", channel=channel)
    system = build_orchestrator_system_prompt(brand, "draft_post", channel=channel)

    assert '"synergy"' in turn and SAMPLE in turn
    assert "may be named" in turn and "builds in public" in turn
    assert "synergy" not in system and SAMPLE not in system
    assert "game-changer" not in system   # the constant left the prefix with the rest


def test_a_carousel_caption_hears_the_samples_but_not_the_text_writers_rules():
    turn = build_post_user_prompt(_brand(**{SAMPLES_KEY: [SAMPLE]}), None, topic="eval", pillar="build",
                                  channel=resolve("tiktok"))

    assert SAMPLE in turn and "VOICE RULES" not in turn


# ---------------------------------------------------------------------------
# The writer and the route
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


def _submit(project, engine, monkeypatch, caption: str, replies: list[str] | None = None) -> tuple[dict, object]:
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))
    session = make_session(f"voice-{uuid4()}", project.id, "draft_post")
    session.channel = "twitter"

    async def _emit(_event):
        return None

    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, _emit, session)}
    draft = {"type": "post", "project_id": str(project.id), "post_dir_slug": f"2026-10-31-{uuid4().hex[:4]}",
             "pillar": "build", "topic": "eval", "caption": caption, "replies": replies or []}
    return json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": draft}))), session


def test_the_writer_refuses_a_default_banned_word_and_names_it(engine, project, monkeypatch):
    result, session = _submit(project, engine, monkeypatch, "Hot take: our eval gate was wrong twice.")

    assert result["status"] == "error" and '"hot take"' in result["message"]
    assert session.post_id is None


def test_the_writer_reads_the_projects_own_list_and_checks_the_reply(engine, db, project, monkeypatch):
    project.content_brand = {RULES_KEY: {"banned_words": ["synergy"]}}
    db.add(project)
    db.commit()

    allowed, _ = _submit(project, engine, monkeypatch, "Hot take: our eval gate was wrong twice.")
    refused, _ = _submit(project, engine, monkeypatch, "Our eval gate was wrong twice.", ["Pure synergy."])

    assert allowed.get("status") != "error", allowed
    assert refused["status"] == "error" and '"synergy"' in refused["message"]
    assert db.query(ContentPost).count() == 1


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_the_brand_route_shows_the_defaults_and_keeps_what_was_saved(db, project, owner):
    api = _api(db, owner)

    fresh = api.get(f"/api/content/brand?project_id={project.id}").json()
    saved = api.put(f"/api/content/brand?project_id={project.id}", json={"content_brand": {
        "tone": "dry", SAMPLES_KEY: [SAMPLE], RULES_KEY: {"banned_words": ["synergy"], "protect_the_edge": False},
    }}).json()

    assert fresh["voice_rules"] == fresh["voice_rules_default"] == VoiceRules().model_dump()
    assert saved["voice_rules"] == {"banned_words": ["synergy"], "no_client_names": True, "protect_the_edge": False}
    assert saved["content_brand"][SAMPLES_KEY] == [SAMPLE]


def test_the_brand_route_holds_the_caps(db, project, owner):
    api = _api(db, owner)

    too_many = api.put(f"/api/content/brand?project_id={project.id}",
                       json={"content_brand": {SAMPLES_KEY: ["a post"] * (MAX_SAMPLES + 1)}})
    too_long = api.put(f"/api/content/brand?project_id={project.id}",
                       json={"content_brand": {SAMPLES_KEY: ["x" * 5000]}})

    assert too_many.status_code == 422 and too_long.status_code == 422
