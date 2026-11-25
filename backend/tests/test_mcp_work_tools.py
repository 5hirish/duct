"""The changes, content and media MCP tools: work an outside agent does on the
person's behalf, every piece of which waits on the person in Duct.

Pinned, in the order they would hurt:

  * no tool approves, applies or publishes, and an outside agent's proposal
    never auto-applies, whatever the project's autonomy;
  * each tool exists only for a connection granted its scope, and a project
    or change set it was not granted reads exactly like a made-up id;
  * a rollback is a request the person carries out, never a revert;
  * a post draft holds to its channel's limit and the project's banned
    words, and lands on the board as a draft, not a publish;
  * an image spends the caller's own key or declines, and comes back as a
    link, never as bytes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

from agents.models import Provider
from agents.tools.execution_tools import _register_executors
from db.session import get_session
from models.activity import ActivityLog
from models.auth import User
from models.content import ContentAsset, ContentPost
from models.execution import ExecutionChangeSet
from models.project import Project
from routes import mcp_server
from service import storage
from service.execution.policy import AUTO_APPLY_ALLOWLIST
from service.execution.registry import EXECUTOR_REGISTRY, ExecutorSpec
from service.images import GeneratedImage
from service.mcp_server import scopes, tools, tools_work
from service.mcp_tokens import mint
from service.membership import ensure_owner_membership
from tests.conftest import make_sqlite_engine

WORK = [scopes.CHANGES, scopes.CONTENT, scopes.MEDIA]


class _Env:
    def __init__(self, session: Session, client: TestClient):
        self.session, self.client = session, client

    def user(self, email: str) -> User:
        user = User(email=email, full_name=email.split("@")[0])
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def project(self, owner: User, **kwargs) -> Project:
        project = Project(user_id=owner.id, name=kwargs.pop("name", "Acme"), slug=f"p-{uuid.uuid4().hex[:8]}", **kwargs)
        self.session.add(project)
        self.session.flush()
        ensure_owner_membership(project, self.session)
        self.session.commit()
        self.session.refresh(project)
        return project

    def token(self, user: User, scopes_=WORK, project_ids=None) -> str:
        return mint(user, "Claude Code", self.session, scopes=scopes_, project_ids=project_ids)[1]

    def rpc(self, token: str, method: str, params: dict | None = None):
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        return self.client.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"})

    def names(self, token: str) -> set[str]:
        return {t["name"] for t in self.rpc(token, "tools/list").json()["result"]["tools"]}

    def call(self, token: str, tool: str, arguments: dict | None = None) -> dict:
        res = self.rpc(token, "tools/call", {"name": tool, "arguments": arguments or {}})
        assert res.status_code == 200, res.text
        return res.json()["result"]


@pytest.fixture
def env():
    engine = make_sqlite_engine(drop_partial_indexes=True)
    session = Session(engine)
    app = FastAPI()
    app.include_router(mcp_server.router)

    def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    yield _Env(session, TestClient(app, raise_server_exceptions=False))
    session.close()
    engine.dispose()


def _error(result: dict) -> str:
    assert result["isError"] is True, result
    return result["structuredContent"]["error"]


def _ok(result: dict) -> dict:
    assert result["isError"] is False, result
    return result["structuredContent"]


# -- what exists, and for whom --------------------------------------------------

def test_no_tool_anywhere_approves_applies_or_publishes():
    forbidden = {"approve", "apply", "publish", "schedule", "connect", "credential", "credentials"}
    for name in tools.TOOLS:
        assert not forbidden & set(name.split("_")), name


def test_each_work_tool_exists_only_with_its_scope(env):
    ana = env.user("ana@acme.example")
    by_scope = {
        scopes.CHANGES: {"list_change_ops", "propose_change_set", "get_change_set", "request_rollback"},
        scopes.CONTENT: {"get_brand", "list_content", "save_post_draft"},
        scopes.MEDIA: {"generate_image"},
    }
    setup_only = env.names(env.token(ana, [scopes.PROJECTS]))
    assert not setup_only & set().union(*by_scope.values())
    for scope, expected in by_scope.items():
        listed = env.names(env.token(ana, [scope]))
        others = set().union(*(v for k, v in by_scope.items() if k != scope))
        assert expected <= listed and not listed & others, scope


def test_a_project_the_connection_was_not_granted_reads_like_a_made_up_one(env):
    ana = env.user("ana@acme.example")
    acme, other = env.project(ana), env.project(ana, name="Other")
    token = env.token(ana, project_ids=[other.id])
    refused = _error(env.call(token, "get_brand", {"project_id": str(acme.id)}))
    made_up = _error(env.call(token, "get_brand", {"project_id": str(uuid.uuid4())}))
    assert refused == made_up
    assert _ok(env.call(token, "get_brand", {"project_id": str(other.id)}))["name"] == "Other"


# -- changes --------------------------------------------------------------------

@pytest.fixture
def fake_executor(monkeypatch):
    """A reversible, allowlisted op, so the only thing that could keep it from
    auto-applying on an assisted project is who proposed it."""
    _register_executors()
    op_type = sorted(AUTO_APPLY_ALLOWLIST)[0]
    real = EXECUTOR_REGISTRY[op_type]
    applied: list[dict] = []
    fake = ExecutorSpec(
        op_type=op_type,
        connector_type=real.connector_type,
        label="fake",
        preview=lambda change, creds: {"diff": "+ one", "current": {}},
        apply=lambda change, creds: applied.append(change) or {"ok": True},
        rollback=lambda change, creds: {"ok": True},
    )
    monkeypatch.setitem(EXECUTOR_REGISTRY, op_type, fake)
    monkeypatch.setattr(tools_work, "resolve_execution_creds", lambda *a, **k: {"refresh_token": "rt", "x": "y"})
    return fake, applied


def _change(spec) -> dict:
    return {"op_type": spec.op_type, "summary": "Add one", "target": {"customer_id": "1"}, "payload": {}}


def test_a_proposal_waits_for_the_person_even_on_an_assisted_project(env, fake_executor):
    spec, applied = fake_executor
    ana = env.user("ana@acme.example")
    acme = env.project(ana, autonomy_level="assisted")
    out = _ok(env.call(env.token(ana), "propose_change_set", {
        "project_id": str(acme.id), "connector_type": spec.connector_type, "account_id": "1",
        "title": "Add one", "context": "Because", "changes": [_change(spec)],
    }))
    assert out["status"] == "proposed" and out["source"] == "mcp"
    assert out["review_url"].split("?")[0].endswith("/execute")
    assert applied == [], "an outside agent's proposal never applies by itself"
    row = env.session.get(ExecutionChangeSet, uuid.UUID(out["change_set_id"]))
    assert (row.project_id, row.status) == (acme.id, "proposed")


def test_a_strangers_change_set_reads_like_a_made_up_one(env):
    ana, bo = env.user("ana@acme.example"), env.user("bo@else.example")
    theirs = ExecutionChangeSet(
        user_id=bo.id, project_id=env.project(bo).id, connector_type="google_ads",
        account_id="1", title="Theirs", changes=[],
    )
    env.session.add(theirs)
    env.session.commit()
    token = env.token(ana)
    stranger = _error(env.call(token, "get_change_set", {"change_set_id": str(theirs.id)}))
    made_up = _error(env.call(token, "get_change_set", {"change_set_id": str(uuid.uuid4())}))
    assert stranger == made_up
    assert _error(env.call(token, "request_rollback", {"change_set_id": str(theirs.id), "reason": "x"})) == made_up


def test_a_rollback_is_asked_for_and_left_to_the_person(env):
    ana = env.user("ana@acme.example")
    acme = env.project(ana)
    row = ExecutionChangeSet(
        user_id=ana.id, project_id=acme.id, connector_type="google_ads", account_id="1",
        title="Budget", status="applied", changes=[],
    )
    env.session.add(row)
    env.session.commit()
    out = _ok(env.call(env.token(ana), "request_rollback", {"change_set_id": str(row.id), "reason": "Spend doubled"}))
    assert out["requested"] is True
    env.session.refresh(row)
    assert row.status == "applied", "nothing reverted by the request"
    asked = env.session.execute(
        select(ActivityLog).where(ActivityLog.action == "change_set.rollback_requested")
    ).scalars().one()
    assert asked.target_id == str(row.id) and "Spend doubled" in asked.summary

    row.status = "proposed"
    env.session.commit()
    assert "Nothing to roll back" in _error(
        env.call(env.token(ana), "request_rollback", {"change_set_id": str(row.id), "reason": "x"})
    )


# -- content --------------------------------------------------------------------

def test_a_post_draft_holds_to_the_channel_and_the_banned_words(env):
    ana = env.user("ana@acme.example")
    acme = env.project(ana, content_brand={"voice_rules": {"banned_words": ["synergy"]}})
    token = env.token(ana)
    base = {"project_id": str(acme.id), "channel": "twitter"}

    too_long = _error(env.call(token, "save_post_draft", {**base, "text": "x" * 300}))
    assert "280" in too_long
    banned = _error(env.call(token, "save_post_draft", {**base, "text": "Pure synergy, shipped."}))
    assert "synergy" in banned
    assert env.session.execute(select(ContentPost)).scalars().all() == [], "a refusal saves nothing"

    out = _ok(env.call(token, "save_post_draft", {**base, "text": "Shipped the new export.", "title": "Export"}))
    post = env.session.get(ContentPost, uuid.UUID(out["post_id"]))
    assert (post.status, post.platforms, post.post_type) == ("draft", ["twitter"], "text")
    assert post.scheduled_at is None and post.publisher_post_id == ""
    assert env.session.execute(select(ActivityLog).where(ActivityLog.action == "post.drafted")).scalars().one()


def test_a_channel_that_needs_media_is_not_offered_for_text(env):
    ana = env.user("ana@acme.example")
    res = env.call(env.token(ana), "save_post_draft", {
        "project_id": str(env.project(ana).id), "channel": "tiktok", "text": "hello",
    })
    assert "channel" in _error(res)


def test_list_content_marks_what_strangers_may_have_written(env):
    ana = env.user("ana@acme.example")
    acme = env.project(ana)
    token = env.token(ana)
    _ok(env.call(token, "save_post_draft", {"project_id": str(acme.id), "channel": "linkedin", "text": "Hello"}))
    listed = _ok(env.call(token, "list_content", {"project_id": str(acme.id)}))
    assert [p["caption"] for p in listed["posts"]] == ["Hello"]
    assert listed["untrusted_fields"] == ["posts[].caption"]


# -- media ----------------------------------------------------------------------

def test_an_image_without_a_key_declines_with_the_providers_that_would_work(env, monkeypatch):
    monkeypatch.setattr(tools_work, "stored_provider_keys", lambda *a, **k: {})
    monkeypatch.setattr(tools_work, "get_model_settings", lambda uid: SimpleNamespace(image_model=""))
    ana = env.user("ana@acme.example")
    message = _error(env.call(env.token(ana), "generate_image", {
        "project_id": str(env.project(ana).id), "prompt": "a lighthouse at dawn",
    }))
    assert all(p in message for p in ("Gemini", "OpenAI", "xAI", "OpenRouter"))


def test_an_image_is_stored_and_returned_as_a_link(env, monkeypatch):
    class _Client:
        async def generate_image(self, request, **_):
            assert request.number_of_images == 1
            return [GeneratedImage(data=b"\x89PNG fake bytes", mime_type="image/png")]

    monkeypatch.setattr(tools_work, "stored_provider_keys", lambda *a, **k: {Provider.GOOGLE_GENAI: "AIza-test"})
    monkeypatch.setattr(tools_work, "image_client_for", lambda provider, key: _Client())
    monkeypatch.setattr(tools_work, "get_model_settings", lambda uid: SimpleNamespace(image_model=""))
    monkeypatch.setattr(storage, "put_image", lambda key, data, mime: f"https://cdn.example/{key}")
    ana = env.user("ana@acme.example")
    acme = env.project(ana)
    result = env.call(env.token(ana), "generate_image", {"project_id": str(acme.id), "prompt": "a lighthouse"})
    out = _ok(result)
    assert out["url"].startswith("https://cdn.example/projects/")
    assert "base64" not in str(result) and "PNG fake" not in str(result)
    asset = env.session.get(ContentAsset, uuid.UUID(out["asset_id"]))
    assert asset.project_id == acme.id
