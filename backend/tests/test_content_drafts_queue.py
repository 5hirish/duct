"""The drafts queue (issue #266): when a text post should go out, what is
still waiting, and a skip that teaches.

What these pin:

  * the slot is the channel's default until the account's own posts with
    numbers say otherwise, and it is a wall-clock hour in the reader's zone;
  * two posts on one channel are never slotted on top of each other;
  * the queue holds only drafts nobody has answered, by the day they came from;
  * a skip discards the draft and leaves a memory the next reflection reads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import routes.content as content_routes
import service.artifact_store as store
import service.auth as auth_service
from agents.content.best_time import REASON_DEFAULT, REASON_HISTORY, next_slot, zone
from agents.content.reflection import ReflectionDraft, save_version
from agents.content.schema import ContentStatus, TEXT_POST_TYPE
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentPost
from models.membership import ProjectMember
from models.memory import ProjectMemory
from models.project import Project
from service import storage
from service.membership import ROLE_OWNER
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
    assert slot.reason == REASON_DEFAULT and slot.posts == 0
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

    assert slot.reason == REASON_HISTORY and slot.posts == 6 and slot.hour == 18
    assert slot.at.astimezone(zone(MADRID)).hour == 18


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
def engine(monkeypatch, tmp_path):
    engine = make_sqlite_engine()

    def _db():
        yield Session(engine)

    monkeypatch.setattr(store, "db_session", _db)
    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage, "get_configs", lambda: cfg)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
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


def _reflection_with_drafts(db, project, owner, day="2026-09-30"):
    draft = ReflectionDraft.model_validate({"title": "A day", "sections": [{
        "id": "s1", "title": "A stream", "happened": "Shipped [gh:pr-1].", "lesson": "Ship small."}]})
    head = save_version(db, project_id=project.id, user_id=owner.id, conversation_id=None, group_id=None,
                        draft=draft, day=datetime.fromisoformat(day).date(),
                        sources=[{"ref": "gh:pr-1", "kind": "pull_request", "title": "PR", "url": ""}])
    link = {"group_id": str(head.group_id), "section_id": "s1", "date": day}
    posts = [
        ContentPost(project_id=project.id, post_dir_slug=f"{day}-{ch}", post_type=TEXT_POST_TYPE,
                    platforms=[ch], caption=f"On {ch}.", status=status, reflection=link)
        for ch, status in (("twitter", ContentStatus.PENDING), ("linkedin", ContentStatus.SCHEDULED))
    ]
    db.add_all(posts)
    db.commit()
    return head, posts


def test_the_queue_holds_only_what_nobody_has_answered(db, project, owner):
    head, (tweet, scheduled) = _reflection_with_drafts(db, project, owner, day=datetime.now(timezone.utc).date().isoformat())

    queue = _api(db, owner).get(f"/api/content/reflection-queue?project_id={project.id}").json()

    assert len(queue) == 1 and queue[0]["group_id"] == str(head.group_id)
    assert [d["id"] for d in queue[0]["drafts"]] == [str(tweet.id)]


def test_a_skip_discards_the_draft_and_remembers_why(db, project, owner):
    _, (tweet, _) = _reflection_with_drafts(db, project, owner)

    res = _api(db, owner).post(f"/api/content/posts/{tweet.id}/skip", json={"reason": "too_revealing"})

    assert res.status_code == 200, res.text
    db.refresh(tweet)
    assert tweet.status == ContentStatus.DISCARDED
    memory = db.exec(select(ProjectMemory).where(ProjectMemory.project_id == project.id,
                                                 ProjectMemory.kind == "decision")).one()
    assert "gave too much away" in memory.title and memory.meta["skip_reason"] == "too_revealing"


def test_only_a_waiting_draft_can_be_skipped(db, project, owner):
    _, (_, scheduled) = _reflection_with_drafts(db, project, owner)

    res = _api(db, owner).post(f"/api/content/posts/{scheduled.id}/skip", json={"reason": "not_true"})

    assert res.status_code == 409


def test_the_best_slot_route_steps_around_a_scheduled_post(db, project, owner):
    api = _api(db, owner)
    first = api.get(f"/api/content/best-slot?project_id={project.id}&channel=twitter&tz={MADRID}").json()
    db.add(ContentPost(project_id=project.id, post_dir_slug="taken", post_type=TEXT_POST_TYPE, platforms=["twitter"],
                       caption="Taken.", status=ContentStatus.SCHEDULED,
                       scheduled_at=datetime.fromisoformat(first["at"])))
    db.commit()

    second = api.get(f"/api/content/best-slot?project_id={project.id}&channel=twitter&tz={MADRID}").json()

    assert first["reason"] == REASON_DEFAULT
    assert datetime.fromisoformat(second["at"]) - datetime.fromisoformat(first["at"]) >= timedelta(days=1)


def test_a_stranger_gets_no_queue_and_no_slot(db, project):
    stranger = User(email="stranger@example.com")
    db.add(stranger)
    db.commit()
    api = _api(db, stranger)

    assert api.get(f"/api/content/reflection-queue?project_id={project.id}").status_code == 404
    assert api.get(f"/api/content/best-slot?project_id={project.id}&channel=twitter").status_code == 404
