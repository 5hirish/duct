"""Unit tests for the versioned artifact store (service + routes)."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.audit.schema import AuditReport, ReportMode  # noqa: E402
from agents.core.events import AgentEvent  # noqa: E402
from config import Configs  # noqa: E402
from db.session import get_session as get_session_dep  # noqa: E402
from models.artifact import Artifact  # noqa: E402
from models.auth import User  # noqa: E402
from models.membership import ProjectMember  # noqa: E402
from models.project import Project  # noqa: E402
import routes.artifacts as artifacts_routes  # noqa: E402
import service.artifact_store as store  # noqa: E402
import service.auth as auth_service  # noqa: E402
import service.storage as storage  # noqa: E402
from service.membership import ROLE_OWNER  # noqa: E402


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


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


@pytest.fixture
def owner(db):
    user = User(email="artifacts-test@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Artifact Test")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


def _freehand_report(url="https://example.com", html="<html><body>audit v1</body></html>"):
    return AuditReport(
        url=url,
        generated_at="2026-08-26T00:00:00Z",
        report_mode=ReportMode.freehand,
        html_report=html,
    )


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------

def test_persist_artifact_version_stores_bytes_and_metadata(local_storage, store_db, project, owner):
    data = b"<html>hello</html>"
    row = store.persist_artifact_version(
        project_id=project.id,
        user_id=owner.id,
        agent_type="audit_seo",
        kind="report",
        content_type="text/html",
        title="SEO audit — example.com",
        filename="audit_v1.html",
        group_id=uuid4(),
        version=1,
        data=data,
        structured_json={"url": "https://example.com"},
        meta={"label": "Initial audit"},
    )
    assert row.storage_key.startswith(f"projects/{project.id}/artifacts/")
    assert row.storage_key.endswith("/v1.html")
    assert row.size_bytes == len(data)
    assert row.checksum == hashlib.sha256(data).hexdigest()
    assert (local_storage / row.storage_key).read_bytes() == data
    assert storage.get_private_bytes(row.storage_key) == data


def test_persist_without_bytes_has_no_storage_key(local_storage, store_db, project, owner):
    row = store.persist_artifact_version(
        project_id=project.id,
        user_id=owner.id,
        agent_type="audit_seo",
        kind="report",
        content_type="application/json",
        title="t",
        filename="t.json",
        group_id=uuid4(),
        version=1,
        data=None,
        structured_json={"structured": True},
    )
    assert row.storage_key == ""
    assert row.size_bytes == 0


async def test_persister_intercepts_report_updated(local_storage, store_db, project, owner, db):
    persister = store.ArtifactPersister(project_id=project.id, user_id=owner.id)
    seen = []

    async def emit(body):
        seen.append(body)

    wrapped = persister.wrap_emit(emit)
    report = _freehand_report()
    await wrapped({
        "event": AgentEvent.REPORT_UPDATED,
        "version_id": 1,
        "label": "Initial audit",
        "payload": report.model_dump(),
    })
    await wrapped({
        "event": AgentEvent.REPORT_UPDATED,
        "version_id": 2,
        "label": "Update 2",
        "payload": _freehand_report(html="<html>v2</html>").model_dump(),
    })
    await asyncio.sleep(0)  # let the (no-op, keyless) summary tasks run

    assert len(seen) == 2  # SSE delivery always happens
    from sqlmodel import select

    rows = list(db.exec(select(Artifact).order_by(Artifact.version)))
    assert [r.version for r in rows] == [1, 2]
    assert all(r.group_id == rows[0].group_id for r in rows)
    assert rows[0].content_type == "text/html"
    assert rows[0].meta["label"] == "Initial audit"
    # html_report is excluded from the row payload — it lives in storage only.
    assert "html_report" not in rows[0].structured_json
    restored = store.load_report_as_versioned(rows[1])
    assert restored.report.html_report == "<html>v2</html>"
    assert restored.version_id == 2


async def test_persister_never_breaks_the_stream(store_db, project, monkeypatch):
    persister = store.ArtifactPersister(project_id=project.id)

    def _boom(**kwargs):
        raise RuntimeError("storage down")

    monkeypatch.setattr(store, "persist_artifact_version", _boom)
    delivered = []

    async def emit(body):
        delivered.append(body)

    wrapped = persister.wrap_emit(emit)
    await wrapped({
        "event": AgentEvent.REPORT_UPDATED,
        "version_id": 1,
        "label": "x",
        "payload": _freehand_report().model_dump(),
    })
    assert len(delivered) == 1  # SSE went through despite the persist failure


def test_latest_versions_collapses_groups(local_storage, store_db, project, owner):
    group = uuid4()
    for version in (1, 2):
        store.persist_artifact_version(
            project_id=project.id, user_id=owner.id, agent_type="audit_seo",
            kind="report", content_type="application/json", title="t", filename="t.json",
            group_id=group, version=version, structured_json={},
        )
    other = store.persist_artifact_version(
        project_id=project.id, user_id=owner.id, agent_type="audit_seo",
        kind="document", content_type="text/markdown", title="doc", filename="d.md",
        group_id=uuid4(), version=1, structured_json={},
    )
    with Session(store_db) as db:
        rows = store.recent_artifact_summaries(db, project.id)
        assert len(rows) == 2
        assert {(r.group_id, r.version) for r in rows} == {(group, 2), (other.group_id, 1)}
        reports_only = store.recent_artifact_summaries(db, project.id, kind="report")
        assert [(r.group_id, r.version) for r in reports_only] == [(group, 2)]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@pytest.fixture
def client(engine, db, owner):
    app = FastAPI()
    app.include_router(artifacts_routes.router, prefix="/api/user/artifacts")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: owner
    return TestClient(app)


@pytest.fixture
def stranger_client(engine, db):
    stranger = User(email="stranger@example.com")
    db.add(stranger)
    db.commit()
    db.refresh(stranger)
    app = FastAPI()
    app.include_router(artifacts_routes.router, prefix="/api/user/artifacts")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: stranger
    return TestClient(app)


def _seed_report(local_storage, store_db, project, owner, *, html=b"<html>r</html>"):
    group = uuid4()
    return store.persist_artifact_version(
        project_id=project.id, user_id=owner.id, agent_type="audit_seo",
        kind="report", content_type="text/html", title="SEO audit",
        filename="audit_v1.html", group_id=group, version=1,
        data=html, structured_json={"url": "https://example.com"},
        meta={"label": "Initial audit", "overall_score": 71},
    )


def test_routes_list_get_content_download(local_storage, store_db, project, owner, client):
    row = _seed_report(local_storage, store_db, project, owner)

    listed = client.get(f"/api/user/artifacts?project_id={project.id}").json()
    assert len(listed) == 1
    assert listed[0]["id"] == str(row.id)
    assert listed[0]["version_count"] == 1
    assert listed[0]["has_content"] is True

    detail = client.get(f"/api/user/artifacts/{row.id}").json()
    assert detail["structured_json"] == {"url": "https://example.com"}

    content = client.get(f"/api/user/artifacts/{row.id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("text/html")
    assert content.content == b"<html>r</html>"

    download = client.get(f"/api/user/artifacts/{row.id}/download")
    assert 'attachment; filename="audit_v1.html"' == download.headers["content-disposition"]


def test_routes_404_for_non_member(local_storage, store_db, project, owner, stranger_client):
    row = _seed_report(local_storage, store_db, project, owner)
    assert stranger_client.get(f"/api/user/artifacts?project_id={project.id}").status_code == 404
    assert stranger_client.get(f"/api/user/artifacts/{row.id}").status_code == 404
    assert stranger_client.get(f"/api/user/artifacts/{row.id}/content").status_code == 404


def test_content_404_when_no_stored_file(local_storage, store_db, project, owner, client):
    row = store.persist_artifact_version(
        project_id=project.id, user_id=owner.id, agent_type="audit_seo",
        kind="report", content_type="application/json", title="t", filename="t.json",
        group_id=uuid4(), version=1, structured_json={"structured": True},
    )
    assert client.get(f"/api/user/artifacts/{row.id}/content").status_code == 404


def test_delete_removes_all_versions_and_files(local_storage, store_db, project, owner, client, db):
    group = uuid4()
    rows = [
        store.persist_artifact_version(
            project_id=project.id, user_id=owner.id, agent_type="audit_seo",
            kind="report", content_type="text/html", title="t", filename=f"v{v}.html",
            group_id=group, version=v, data=f"<html>v{v}</html>".encode(),
        )
        for v in (1, 2)
    ]
    resp = client.delete(f"/api/user/artifacts/{rows[1].id}")
    assert resp.status_code == 204
    from sqlmodel import select

    assert list(db.exec(select(Artifact))) == []
    for row in rows:
        assert not (local_storage / row.storage_key).exists()
