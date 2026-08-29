"""Activity log tests — writer resilience, transition call sites, feed route."""

from __future__ import annotations

from uuid import uuid4

import pytest

from tests.conftest import make_sqlite_engine
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

from config import Configs
from db.session import get_session as get_session_dep
from models.activity import ActivityLog
from models.auth import User
from models.execution import AUTONOMY_ASSISTED, ExecutionChangeSet
from models.membership import ProjectMember
from models.project import Project
import routes.activity as activity_routes
import service.artifact_store as store
import service.auth as auth_service
import service.execution.policy as policy
import service.storage as storage
from service.activity import log_activity
from service.execution.registry import EXECUTOR_REGISTRY, ExecutorSpec, register_executor
from service.execution.service import (
    _log_gtm_publishes,
    propose_change_set,
    rollback_change_set,
)
from service.membership import ROLE_OWNER


# ---------------------------------------------------------------------------
# Fixtures (test_artifact_store / test_execution_policy patterns)
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    engine = make_sqlite_engine()
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def owner(db):
    user = User(email="activity-test@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Activity Test", autonomy_level=AUTONOMY_ASSISTED)
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def fake_ops(monkeypatch):
    spec = ExecutorSpec(
        op_type="testconn.safe",
        connector_type="testconn",
        label="Safe op",
        preview=lambda change, creds: {"current": {}, "diff": "d", "warnings": []},
        apply=lambda change, creds: {"rollback": {"handle": "h"}},
        rollback=lambda change, creds: {"restored": True},
    )
    register_executor(spec)
    monkeypatch.setattr(
        policy, "AUTO_APPLY_ALLOWLIST", policy.AUTO_APPLY_ALLOWLIST | {"testconn.safe"}
    )
    yield spec
    EXECUTOR_REGISTRY.pop("testconn.safe", None)


def _rows(db, action=None):
    stmt = select(ActivityLog).order_by(ActivityLog.created_at)
    rows = list(db.execute(stmt).scalars())
    return [r for r in rows if action is None or r.action == action]


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def test_log_activity_writes_row(db, project, owner):
    log_activity(
        db,
        category="execution",
        action="change_set.proposed",
        source="agent",
        project_id=project.id,
        user_id=owner.id,
        agent_type="audit_seo",
        connector_type="google_ads",
        target_type="change_set",
        target_id="abc",
        summary="Proposed things",
        data={"n": 2},
    )
    (row,) = _rows(db)
    assert row.category == "execution"
    assert row.source == "agent"
    assert row.project_id == project.id
    assert row.data == {"n": 2}
    assert row.summary == "Proposed things"


def test_log_activity_swallows_failures():
    class _Broken:
        def add(self, row):
            raise RuntimeError("db down")

        def rollback(self):
            raise RuntimeError("still down")

    # Must not raise — the audit trail never breaks the write it records.
    log_activity(_Broken(), category="execution", action="x")


# ---------------------------------------------------------------------------
# Execution transitions
# ---------------------------------------------------------------------------

def test_auto_applied_set_writes_proposed_and_auto_applied_rows(db, owner, project, fake_ops):
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="a1",
        account_name="A",
        title="Safe changes",
        context="why",
        changes=[{"op_type": "testconn.safe", "summary": "s", "target": {}, "payload": {}}],
        creds={},
        project_id=project.id,
        conversation_id=uuid4(),
        agent_type="audit_seo",
        source="agent",
    )
    assert row.status == "applied"
    proposed = _rows(db, "change_set.proposed")
    auto = _rows(db, "change_set.auto_applied")
    assert len(proposed) == 1 and proposed[0].source == "agent"
    assert len(auto) == 1 and auto[0].source == "auto"
    for r in proposed + auto:
        assert r.project_id == project.id
        assert r.conversation_id == row.conversation_id
        assert r.target_id == str(row.id)


def test_rollback_records_actor(db, owner, project, fake_ops):
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="a1",
        account_name="A",
        title="Safe changes",
        context="",
        changes=[{"op_type": "testconn.safe", "summary": "s", "target": {}, "payload": {}}],
        creds={},
        project_id=project.id,
        agent_type="audit_seo",
        source="agent",
    )
    rollback_change_set(db, row, {}, actor="agent")
    (rolled,) = _rows(db, "change_set.rolled_back")
    assert rolled.source == "agent"
    assert "1 reverted" in rolled.summary


def test_gtm_publish_writes_deploy_log_row(db, owner, project):
    cs = ExecutionChangeSet(
        user_id=owner.id,
        project_id=project.id,
        agent_type="audit_seo",
        connector_type="gtm",
        account_id="11",
        title="Ship GTM fix",
        changes=[],
    )
    db.add(cs)
    db.commit()
    db.refresh(cs)

    applied_change = {
        "op_type": "gtm.publish_version",
        "status": "applied",
        "result": {
            "published_version_id": "8",
            "rollback": {"container_path": "accounts/1/containers/2", "prior_live_version_id": "7"},
        },
    }
    _log_gtm_publishes(db, cs, [applied_change], source="user")
    (published,) = _rows(db, "gtm.published")
    assert published.data == {"published_version_id": "8", "prior_live_version_id": "7"}
    assert "version 8" in published.summary and "prior live: 7" in published.summary

    rolled_change = {
        "op_type": "gtm.publish_version",
        "status": "rolled_back",
        "rollback_result": {"republished_version_id": "7"},
    }
    _log_gtm_publishes(db, cs, [rolled_change], source="user")
    republished = _rows(db, "gtm.published")[-1]
    assert republished.data == {"published_version_id": "7", "rollback": True}


# ---------------------------------------------------------------------------
# Artifact writes
# ---------------------------------------------------------------------------

@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage, "get_configs", lambda: cfg)
    return tmp_path


@pytest.fixture
def store_db(engine, monkeypatch):
    def _fake_db():
        yield Session(engine)

    monkeypatch.setattr(store, "db_session", _fake_db)
    return engine


def test_artifact_versions_write_activity_rows(db, local_storage, store_db, project, owner):
    group = uuid4()
    conversation = uuid4()
    store.persist_artifact_version(
        project_id=project.id, user_id=owner.id, agent_type="audit_seo",
        kind="document", content_type="text/markdown", title="Keyword memo",
        filename="memo_v1.md", group_id=group, version=1,
        conversation_id=conversation, data=b"# memo",
    )
    store.persist_artifact_version(
        project_id=project.id, user_id=owner.id, agent_type="audit_seo",
        kind="document", content_type="text/markdown", title="Keyword memo",
        filename="memo_v2.md", group_id=group, version=2,
        conversation_id=conversation, data=b"# memo v2",
        meta={"label": "Added long-tails"},
        activity_source="user",
    )
    (created,) = _rows(db, "artifact.created")
    (versioned,) = _rows(db, "artifact.version_added")
    assert created.source == "agent" and "Keyword memo" in created.summary
    assert versioned.source == "user" and "v2" in versioned.summary
    assert created.conversation_id == conversation
    assert created.data["group_id"] == str(group)


# ---------------------------------------------------------------------------
# Feed route
# ---------------------------------------------------------------------------

def _make_client(engine, db, user):
    app = FastAPI()
    app.include_router(activity_routes.router, prefix="/api/user/activity")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app)


def _seed_rows(db, project, owner, n=3, conversation_id=None, category="execution"):
    for i in range(n):
        log_activity(
            db,
            category=category,
            action=f"change_set.step{i}",
            source="agent",
            project_id=project.id,
            user_id=owner.id,
            conversation_id=conversation_id,
            summary=f"row {i}",
        )


def test_feed_lists_project_rows_newest_first(engine, db, project, owner):
    _seed_rows(db, project, owner, n=3)
    client = _make_client(engine, db, owner)
    res = client.get(f"/api/user/activity?project_id={project.id}")
    assert res.status_code == 200
    body = res.json()
    assert [r["summary"] for r in body["items"]] == ["row 2", "row 1", "row 0"]
    assert body["next_before"] is None


def test_feed_requires_membership(engine, db, project, owner):
    _seed_rows(db, project, owner, n=1)
    stranger = User(email="stranger@example.com")
    db.add(stranger)
    db.commit()
    db.refresh(stranger)
    client = _make_client(engine, db, stranger)
    res = client.get(f"/api/user/activity?project_id={project.id}")
    assert res.status_code == 404


def test_feed_filters_by_conversation_and_category(engine, db, project, owner):
    conversation = uuid4()
    _seed_rows(db, project, owner, n=2)  # no conversation
    _seed_rows(db, project, owner, n=1, conversation_id=conversation)
    _seed_rows(db, project, owner, n=1, conversation_id=conversation, category="artifact")
    client = _make_client(engine, db, owner)

    res = client.get(f"/api/user/activity?project_id={project.id}&conversation_id={conversation}")
    assert len(res.json()["items"]) == 2

    res = client.get(
        f"/api/user/activity?project_id={project.id}&conversation_id={conversation}&category=artifact"
    )
    items = res.json()["items"]
    assert len(items) == 1 and items[0]["category"] == "artifact"


def test_feed_keyset_pagination(engine, db, project, owner):
    _seed_rows(db, project, owner, n=5)
    client = _make_client(engine, db, owner)
    first = client.get(f"/api/user/activity?project_id={project.id}&limit=2").json()
    assert len(first["items"]) == 2 and first["next_before"]
    second = client.get(
        f"/api/user/activity?project_id={project.id}&limit=2&before={first['next_before']}"
    ).json()
    assert len(second["items"]) == 2
    seen = {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    assert not seen  # no overlap between pages


def test_feed_rejects_bad_before(engine, db, project, owner):
    client = _make_client(engine, db, owner)
    res = client.get(f"/api/user/activity?project_id={project.id}&before=yesterday")
    assert res.status_code == 422
