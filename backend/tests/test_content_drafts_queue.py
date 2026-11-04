"""The drafts queue (issue #266): when a draft should go out, what is still
waiting, and a skip that teaches.

What these pin:

  * the slot is the channel's default until the account's own posts with
    numbers say otherwise, and it is a wall-clock hour in the reader's zone;
  * two posts on one channel are never slotted on top of each other;
  * the queue's source holds only drafts nobody has answered, any channel;
  * a skip discards the draft and leaves a memory the content agent's next
    run reads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import routes.content as content_routes
import service.auth as auth_service
from agents.content.best_time import SlotReason, next_slot, zone
from agents.content.schema import TEXT_POST_TYPE, ContentStatus
from agents.registry import AgentType
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentPost
from models.membership import ProjectMember
from models.memory import ProjectMemory
from models.project import Project
from service.membership import ROLE_OWNER
from service.memory import build_memory_context
from tests.conftest import make_sqlite_engine

MADRID = "Europe/Madrid"
# A Wednesday, 10:00 in Madrid.
NOW = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)


def _posted(hour_local: int, views: int, day: int = 1):
    at = datetime(2026, 9, day, hour_local, 0, tzinfo=zone(MADRID)).astimezone(timezone.utc)
    return SimpleNamespace(perf={"views": views}, posted_at=at)


# ---------------------------------------------------------------------------
# The slot
# ---------------------------------------------------------------------------


def test_with_no_history_x_gets_the_next_weekday_morning_in_the_readers_zone():
    slot = next_slot("twitter", posts=[], taken=[], now=NOW, tz_name=MADRID)

    local = slot.at.astimezone(zone(MADRID))
    assert slot.reason == SlotReason.DEFAULT and slot.posts == 0
    # 09:00 has passed today in Madrid, so tomorrow (a Thursday) at 09:00.
    assert (local.date().isoformat(), local.hour) == ("2026-10-01", 9)


def test_linkedin_waits_for_its_mid_week_morning():
    # Friday: LinkedIn's default runs Tuesday to Thursday, so the next is Tuesday.
    friday = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    local = next_slot("linkedin", posts=[], taken=[], now=friday, tz_name=MADRID).at.astimezone(zone(MADRID))

    assert (local.strftime("%A"), local.hour) == ("Tuesday", 8)


def test_the_accounts_own_best_hour_wins_once_there_are_enough_posts():
    posts = [_posted(18, 900, d) for d in (1, 2, 3)] + [_posted(9, 100, d) for d in (4, 5, 6)]

    slot = next_slot("twitter", posts=posts, taken=[], now=NOW, tz_name=MADRID)

    assert slot.reason == SlotReason.HISTORY and slot.posts == 6 and slot.hour == 18
    assert slot.at.astimezone(zone(MADRID)).hour == 18


def test_a_visual_channel_learns_its_hour_the_same_way():
    # PostBridge syncs TikTok numbers, so its history arrives without typing.
    posts = [_posted(20, 5000, d) for d in (1, 2, 3)] + [_posted(12, 800, d) for d in (4, 5)]

    assert next_slot("tiktok", posts=[], taken=[], now=NOW, tz_name=MADRID).reason == SlotReason.DEFAULT
    slot = next_slot("tiktok", posts=posts, taken=[], now=NOW, tz_name=MADRID)
    assert slot.reason == SlotReason.HISTORY and slot.hour == 20


def test_a_slot_already_taken_on_the_channel_moves_to_the_next_day():
    first = next_slot("twitter", posts=[], taken=[], now=NOW, tz_name=MADRID)
    second = next_slot("twitter", posts=[], taken=[first.at], now=NOW, tz_name=MADRID)

    assert second.at - first.at == timedelta(days=1)


def test_an_unknown_timezone_reads_as_utc_rather_than_failing():
    assert next_slot("twitter", posts=[], taken=[], now=NOW, tz_name="Mars/Olympus").at.hour == 9


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


@pytest.fixture
def owner(db):
    row = User(email="builder@example.com")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Duct", slug="duct")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _post(db, project, channel, status, *, topic="", **fields) -> ContentPost:
    row = ContentPost(
        project_id=project.id, post_dir_slug=f"{channel}-{status}-{topic or 'x'}",
        post_type=TEXT_POST_TYPE if channel in ("twitter", "linkedin") else "carousel",
        platforms=[channel], topic=topic, caption=f"On {channel}.", status=status, **fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_the_queue_holds_only_what_nobody_has_answered(db, project, owner):
    waiting = [
        _post(db, project, "twitter", ContentStatus.DRAFT, topic="chat draft"),
        _post(db, project, "tiktok", ContentStatus.DRAFT, topic="plan day draft"),
    ]
    for status in (ContentStatus.PENDING, ContentStatus.SCHEDULED, ContentStatus.POSTED, ContentStatus.DISCARDED):
        _post(db, project, "linkedin", status, topic=status)

    queue = _api(db, owner).get(f"/api/content/posts?project_id={project.id}&status=draft").json()

    assert {p["id"] for p in queue} == {str(p.id) for p in waiting}


def test_a_skip_discards_the_draft_and_remembers_why(db, project, owner):
    tweet = _post(db, project, "twitter", ContentStatus.DRAFT, topic="Why we moved our eval")

    res = _api(db, owner).post(f"/api/content/posts/{tweet.id}/skip", json={"reason": "too_revealing"})

    assert res.status_code == 200, res.text
    assert res.json()["status"] == ContentStatus.DISCARDED
    db.refresh(tweet)
    assert tweet.status == ContentStatus.DISCARDED
    memory = db.exec(select(ProjectMemory).where(ProjectMemory.project_id == project.id,
                                                 ProjectMemory.kind == "feedback")).one()
    assert "Why we moved our eval" in memory.title and "gave too much away" in memory.title
    assert memory.meta["skip_reason"] == "too_revealing"


def test_the_content_agents_next_run_reads_the_skip(db, project, owner):
    draft = _post(db, project, "linkedin", ContentStatus.DRAFT, topic="Our pricing maths")
    _api(db, owner).post(f"/api/content/posts/{draft.id}/skip", json={"reason": "not_true"})

    # The same call the content runner's _memory_block makes.
    context = build_memory_context(
        db, project_id=project.id, user_id=owner.id,
        agent_type=str(AgentType.TIKTOK_STUDIO), artifact_kind=None,
    )

    assert "Our pricing maths" in context.text and "it was not true" in context.text


def test_skips_never_crowd_goals_out_of_the_pinned_digest(db, project, owner):
    """The digest pins the five newest goals and decisions. Skips are feedback,
    so a run of them leaves a standing goal where the agent always reads it."""
    from service.memory import SECTION_PINNED, remember

    remember(db, kind="goal", title="Reach 1,000 LinkedIn followers by March",
             project_id=project.id, user_id=owner.id)
    for i in range(6):
        draft = _post(db, project, "linkedin", ContentStatus.DRAFT, topic=f"Draft {i}")
        _api(db, owner).post(f"/api/content/posts/{draft.id}/skip", json={"reason": "not_interesting"})

    context = build_memory_context(
        db, project_id=project.id, user_id=owner.id,
        agent_type=str(AgentType.TIKTOK_STUDIO), artifact_kind=None,
    )
    pinned = context.text.split(f"## {SECTION_PINNED}", 1)[1].split("\n## ", 1)[0]
    assert "1,000 LinkedIn followers" in pinned
    assert "Draft 0" not in pinned


def test_only_a_draft_that_has_not_gone_out_can_be_skipped(db, project, owner):
    scheduled = _post(db, project, "twitter", ContentStatus.SCHEDULED)

    res = _api(db, owner).post(f"/api/content/posts/{scheduled.id}/skip", json={"reason": "not_true"})

    assert res.status_code == 409


def test_a_skip_needs_one_of_the_five_reasons(db, project, owner):
    draft = _post(db, project, "twitter", ContentStatus.DRAFT)

    res = _api(db, owner).post(f"/api/content/posts/{draft.id}/skip", json={"reason": "meh"})

    assert res.status_code == 422


def test_the_best_slot_route_steps_around_a_scheduled_post(db, project, owner):
    api = _api(db, owner)
    first = api.get(f"/api/content/best-slot?project_id={project.id}&channel=twitter&tz={MADRID}").json()
    _post(db, project, "twitter", ContentStatus.SCHEDULED, scheduled_at=datetime.fromisoformat(first["at"]))

    second = api.get(f"/api/content/best-slot?project_id={project.id}&channel=twitter&tz={MADRID}").json()

    assert first["reason"] == SlotReason.DEFAULT
    assert datetime.fromisoformat(second["at"]) - datetime.fromisoformat(first["at"]) >= timedelta(days=1)


def test_a_stranger_gets_no_slot_and_cannot_skip(db, project):
    draft = _post(db, project, "twitter", ContentStatus.DRAFT)
    stranger = User(email="stranger@example.com")
    db.add(stranger)
    db.commit()
    api = _api(db, stranger)

    assert api.get(f"/api/content/best-slot?project_id={project.id}&channel=twitter").status_code == 404
    assert api.post(f"/api/content/posts/{draft.id}/skip", json={"reason": "not_true"}).status_code == 404
    db.refresh(draft)
    assert draft.status == ContentStatus.DRAFT
