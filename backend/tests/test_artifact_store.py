"""Unit tests for the versioned artifact store (service + routes)."""

from __future__ import annotations

import asyncio
import hashlib
from uuid import uuid4

import pytest

from tests.conftest import make_sqlite_engine
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from agents.audit.schema import AuditReport, ReportMode
from agents.core.events import AgentEvent
from config import Configs
from db.session import get_session as get_session_dep
from models.artifact import Artifact
from models.auth import User
from models.membership import ProjectMember
from models.project import Project
import routes.artifacts as artifacts_routes
import service.artifact_store as store
import service.auth as auth_service
import service.storage as storage
from service.membership import ROLE_OWNER


@pytest.fixture
def engine():
    engine = make_sqlite_engine()
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
        "event": AgentEvent.ARTIFACT_VERSION,
        "version_id": 1,
        "label": "Initial audit",
        "payload": report.model_dump(),
    })
    await wrapped({
        "event": AgentEvent.ARTIFACT_VERSION,
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


async def test_persister_skips_replayed_versions(local_storage, store_db, project, owner, db):
    persister = store.ArtifactPersister(project_id=project.id, user_id=owner.id)
    wrapped = persister.wrap_emit(lambda body: asyncio.sleep(0))
    await wrapped({
        "event": AgentEvent.ARTIFACT_VERSION,
        "version_id": 1,
        "label": "Initial audit",
        "payload": _freehand_report().model_dump(),
        "replay": True,  # rehydrated on resume — already stored
    })
    from sqlmodel import select

    assert list(db.exec(select(Artifact))) == []


async def test_persister_resumes_existing_group(local_storage, store_db, project, owner, db):
    first = store.ArtifactPersister(project_id=project.id, user_id=owner.id)
    wrapped = first.wrap_emit(lambda body: asyncio.sleep(0))
    await wrapped({
        "event": AgentEvent.ARTIFACT_VERSION, "version_id": 1, "label": "Initial audit",
        "payload": _freehand_report().model_dump(),
    })
    # A resumed session passes the stored group_id — v2 extends the same artifact.
    second = store.ArtifactPersister(
        project_id=project.id, user_id=owner.id, group_id=first.group_id
    )
    wrapped2 = second.wrap_emit(lambda body: asyncio.sleep(0))
    await wrapped2({
        "event": AgentEvent.ARTIFACT_VERSION, "version_id": 2, "label": "Update 2",
        "payload": _freehand_report(html="<html>v2</html>").model_dump(),
    })
    await asyncio.sleep(0)
    from sqlmodel import select

    rows = list(db.exec(select(Artifact).order_by(Artifact.version)))
    assert [(r.group_id, r.version) for r in rows] == [(first.group_id, 1), (first.group_id, 2)]


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
        "event": AgentEvent.ARTIFACT_VERSION,
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


def _seed_text_versions(store_db, project, owner, contents, content_type="text/markdown", kind="memo"):
    group = uuid4()
    rows = []
    for v, text in enumerate(contents, start=1):
        rows.append(store.persist_artifact_version(
            project_id=project.id, user_id=owner.id, agent_type="audit_seo",
            kind=kind, content_type=content_type, title="Memo", filename=f"memo_v{v}.md",
            group_id=group, version=v, data=text.encode(), slug="memo",
            meta={"label": f"v{v} label"},
        ))
    return rows


def test_restore_promotes_snapshot_to_new_head(local_storage, store_db, project, owner, client, db):
    v1, _v2 = _seed_text_versions(store_db, project, owner, ["alpha", "beta"])
    resp = client.post(f"/api/user/artifacts/{v1.id}/restore")
    assert resp.status_code == 201
    head = resp.json()
    assert head["version"] == 3
    assert head["meta"]["label"] == "Restored from v1"
    restored = client.get(f"/api/user/artifacts/{head['id']}/content")
    assert restored.content == b"alpha"  # history preserved, head restored


def test_diff_between_versions(local_storage, store_db, project, owner, client):
    _v1, v2 = _seed_text_versions(store_db, project, owner, ["line one\nline two", "line one\nline 2!"])
    payload = client.get(f"/api/user/artifacts/{v2.id}/diff").json()
    assert payload["base_version"] == 1 and payload["target_version"] == 2
    assert "-line two" in payload["diff"] and "+line 2!" in payload["diff"]


def test_resolve_by_slug_and_group(local_storage, store_db, project, owner, client):
    v1, v2 = _seed_text_versions(store_db, project, owner, ["a", "b"])
    by_slug = client.get(f"/api/user/artifacts/resolve?project_id={project.id}&ref=memo").json()
    assert by_slug["id"] == str(v2.id)  # latest version wins
    by_group = client.get(
        f"/api/user/artifacts/resolve?project_id={project.id}&ref={v1.group_id}"
    ).json()
    assert by_group["id"] == str(v2.id)
    by_url = client.get(
        f"/api/user/artifacts/resolve?project_id={project.id}&ref=https://app.getduct.ai/artifacts/{v1.id}"
    ).json()
    assert by_url["id"] == str(v2.id)


def test_export_csv_and_format_gating(local_storage, store_db, project, owner, client):
    table = '{"columns": ["kw", "vol"], "rows": [["seo audit", 1200], ["ai seo", 480]]}'
    (row,) = _seed_text_versions(
        store_db, project, owner, [table],
        content_type="application/vnd.duct.table+json", kind="dataset",
    )
    resp = client.get(f"/api/user/artifacts/{row.id}/export?format=csv")
    assert resp.status_code == 200
    assert resp.content.decode().splitlines()[0] == "kw,vol"
    assert 'attachment; filename="memo_v1.csv"' == resp.headers["content-disposition"]
    # PDF is for structured reports only.
    assert client.get(f"/api/user/artifacts/{row.id}/export?format=pdf").status_code == 422


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
