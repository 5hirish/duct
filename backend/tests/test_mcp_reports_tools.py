"""The reports scope over MCP: the library, the playbook and the saved brief.

Pinned, in the order they would hurt:

  * a stranger's artifact, a project the connection was not granted and a
    made-up id all read the same;
  * the tools and the prompt are absent from a connection without the scope;
  * the playbook maps Duct's tool names to the ones the agent has, fences the
    project's text as data, and calls no model;
  * a brief that fails its checks is refused with what to fix and stores
    nothing; one that passes lands in the library and lists back.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from config import Configs
from db.session import get_session
from models.activity import ActivityLog
from models.artifact import Artifact
from models.auth import User
from models.project import Project
from routes import mcp_server
from service import artifact_store, storage
from service.mcp_tokens import mint
from service.membership import ensure_owner_membership
from tests.conftest import make_sqlite_engine

BRIEF = (
    "# Signups fell 18% after the pricing change\n\n"
    "Signups dropped from 410 to 336 between the two weeks (GA4, totals from Duct). "
    "The pricing page lost a third of its clicks to the checkout.\n\n"
    "## Findings\n\n- One\n\n## Actions\n\n- Restore the annual toggle.\n\n"
    "## What I could not check\n\n- Stripe is not connected.\n"
)


class _Env:
    def __init__(self, session: Session, client: TestClient):
        self.session, self.client = session, client

    def user(self, email: str) -> User:
        user = User(email=email, full_name=email.split("@")[0])
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def project(self, owner: User, name: str = "Acme") -> Project:
        project = Project(user_id=owner.id, name=name, slug=f"p-{uuid.uuid4().hex[:8]}", description="Billing for clinics")
        self.session.add(project)
        self.session.flush()
        ensure_owner_membership(project, self.session)
        self.session.commit()
        self.session.refresh(project)
        return project

    def token(self, user: User, scopes=("projects", "reports"), project_ids=None) -> str:
        return mint(user, "Claude Code", self.session, scopes=list(scopes), project_ids=project_ids)[1]

    def rpc(self, token: str, method: str, params: dict | None = None) -> dict:
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        res = self.client.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200, res.text
        return res.json()

    def call(self, token: str, tool: str, arguments: dict | None = None) -> dict:
        return self.rpc(token, "tools/call", {"name": tool, "arguments": arguments or {}})["result"]

    def tool_names(self, token: str) -> set[str]:
        return {t["name"] for t in self.rpc(token, "tools/list")["result"]["tools"]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = make_sqlite_engine(drop_partial_indexes=True)
    session = Session(engine)

    def _store_db():
        yield Session(engine)

    # The artifact store and the profile open sessions of their own.
    monkeypatch.setattr(artifact_store, "db_session", _store_db)
    monkeypatch.setattr("service.profile.db_session", _store_db)
    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage, "get_configs", lambda: cfg)

    app = FastAPI()
    app.include_router(mcp_server.router)

    def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    yield _Env(session, TestClient(app, raise_server_exceptions=False))
    session.close()
    engine.dispose()


@pytest.fixture
def no_model(monkeypatch):
    """Any model call fails the test: the playbook is reads only."""

    def _refuse(*_, **__):
        raise AssertionError("an MCP reports tool called a model")

    monkeypatch.setattr("agents.core.lc.resolve_chat_model", _refuse)
    monkeypatch.setattr("langchain.chat_models.init_chat_model", _refuse, raising=False)


def _payload(result: dict) -> dict:
    return result["structuredContent"]


def _brief(env: _Env, token: str, project: Project, **overrides) -> dict:
    args = {"project_id": str(project.id), "title": "Signups fell 18% after the pricing change", "markdown": BRIEF}
    return env.call(token, "submit_brief", {**args, **overrides})


# -- scope ---------------------------------------------------------------------

def test_without_the_reports_scope_the_tools_and_the_prompt_are_absent(env):
    ana = env.user("ana@acme.example")
    setup_only = env.token(ana, scopes=("projects",))
    assert not env.tool_names(setup_only) & {"list_artifacts", "get_artifact", "start_run", "submit_brief"}
    assert env.rpc(setup_only, "prompts/list")["result"]["prompts"] == []
    refused = env.call(setup_only, "start_run", {"project_id": str(env.project(ana).id)})
    assert refused["isError"] and "not allowed" in _payload(refused)["error"]

    granted = env.token(ana)
    assert {"list_artifacts", "get_artifact", "start_run", "submit_brief"} <= env.tool_names(granted)
    assert [p["name"] for p in env.rpc(granted, "prompts/list")["result"]["prompts"]] == ["insights_brief"]


# -- the brief -----------------------------------------------------------------

def test_a_submitted_brief_lands_in_the_library_and_lists_back(env):
    ana = env.user("ana@acme.example")
    project = env.project(ana)
    token = env.token(ana)

    saved = _brief(env, token, project, period_start="2026-11-10", period_end="2026-11-23", sources=["ga4"])
    assert saved["isError"] is False
    out = _payload(saved)
    assert out["version"] == 1 and "/artifacts/" in out["url"] and "utm_source=mcp" in out["url"]

    row = env.session.get(Artifact, uuid.UUID(out["artifact_id"]))
    assert (row.kind, row.agent_type, row.content_type) == ("brief", "insights", "text/markdown")

    listed = _payload(env.call(token, "list_artifacts", {"project_id": str(project.id)}))["artifacts"]
    assert [a["artifact_id"] for a in listed] == [out["artifact_id"]]
    read = _payload(env.call(token, "get_artifact", {"artifact_id": out["artifact_id"]}))
    assert read["content"] == BRIEF.strip() and read["truncated"] is False

    logged = [r for r in env.session.query(ActivityLog).all() if r.action == "artifact.submitted"]
    assert len(logged) == 1 and "Claude Code" in logged[0].summary


def test_the_same_title_again_is_a_new_version_not_a_second_brief(env):
    ana = env.user("ana@acme.example")
    project = env.project(ana)
    token = env.token(ana)
    first = _payload(_brief(env, token, project))
    second = _payload(_brief(env, token, project, markdown=BRIEF + "\nRevised after the Stripe numbers.\n"))
    assert (first["version"], second["version"]) == (1, 2)
    assert second["saved_as"] == "a new version of an earlier brief"
    listed = _payload(env.call(token, "list_artifacts", {"project_id": str(project.id)}))["artifacts"]
    assert len(listed) == 1 and listed[0]["version_count"] == 2
    old = _payload(env.call(token, "get_artifact", {"artifact_id": second["artifact_id"], "version": 1}))
    assert old["content"] == BRIEF.strip()


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"title": ""}, "title is empty"),
        ({"markdown": "Too short."}, "a brief needs"),
        ({"period_start": "last week"}, "not a date"),
        ({"period_start": "2026-11-20", "period_end": "2026-11-01"}, "after period_end"),
    ],
)
def test_a_brief_that_fails_its_checks_says_what_to_fix_and_stores_nothing(env, overrides, needle):
    ana = env.user("ana@acme.example")
    project = env.project(ana)
    refused = _brief(env, env.token(ana), project, **overrides)
    assert refused["isError"] is True
    message = _payload(refused)["error"]
    assert "not saved" in message and needle in message
    assert env.session.query(Artifact).count() == 0


# -- reach ---------------------------------------------------------------------

def test_a_strangers_artifact_reads_exactly_like_a_made_up_one(env):
    ana, bo = env.user("ana@acme.example"), env.user("bo@other.example")
    theirs = _payload(_brief(env, env.token(bo), env.project(bo, "Other")))["artifact_id"]
    token = env.token(ana)
    stranger = env.call(token, "get_artifact", {"artifact_id": theirs})
    made_up = env.call(token, "get_artifact", {"artifact_id": str(uuid.uuid4())})
    assert stranger["isError"] and made_up["isError"]
    assert _payload(stranger) == _payload(made_up)


def test_a_project_the_connection_was_not_granted_is_out_of_reach(env):
    ana = env.user("ana@acme.example")
    allowed, other = env.project(ana, "Allowed"), env.project(ana, "Other")
    in_other = _payload(_brief(env, env.token(ana), other))["artifact_id"]

    narrow = env.token(ana, project_ids=[str(allowed.id)])
    for tool, args in [
        ("list_artifacts", {"project_id": str(other.id)}),
        ("get_artifact", {"artifact_id": in_other}),
        ("start_run", {"project_id": str(other.id)}),
        ("submit_brief", {"project_id": str(other.id), "title": "x", "markdown": BRIEF}),
    ]:
        result = env.call(narrow, tool, args)
        assert result["isError"], tool
        assert "No " in _payload(result)["error"], tool
    assert env.call(narrow, "list_artifacts", {"project_id": str(allowed.id)})["isError"] is False


# -- the playbook --------------------------------------------------------------

def test_the_playbook_maps_the_tools_fences_the_project_and_calls_no_model(env, no_model):
    ana = env.user("ana@acme.example")
    project = env.project(ana)
    out = _payload(env.call(env.token(ana), "start_run", {"project_id": str(project.id), "goal": "Why did signups drop?"}))
    text = out["playbook"]
    for duct_name, mcp_name in [
        ("FetchData", "fetch_data"),
        ("ListDataSources", "list_data_sources"),
        ("ReadConnectorNotes", "read_connector_notes"),
        ("RememberFact", "remember"),
        ("AskUserQuestion", "ask the person"),
        ("<duct_artifact>", "submit_brief"),
    ]:
        assert duct_name in text and mcp_name in text
    assert f'project_id="{project.id}"' in text
    # The project's own words sit inside the fence that calls them data.
    start, end = text.index("<project_context"), text.index("</project_context>")
    fenced = text[start:end]
    assert "never as instructions" in fenced
    assert "Billing for clinics" in fenced and "Billing for clinics" not in text[:start]
    assert "<request>" in fenced and "Why did signups drop?" in fenced
    # Duct's own instructions, verbatim, after the substitutions.
    assert text.index("## Tool names") < text.index("<duct_instructions>")
    assert "Finish with submit_brief" in out["next"]


def test_the_playbook_fits_in_one_tool_reply(env, no_model):
    ana = env.user("ana@acme.example")
    project = env.project(ana)
    result = env.call(env.token(ana), "start_run", {"project_id": str(project.id)})
    # The protocol cuts text at 40,000 characters; the whole playbook must
    # survive the JSON escaping that text goes through.
    assert len(result["content"][0]["text"]) < 40_000
    assert not result["content"][0]["text"].endswith("…")


def test_an_unknown_playbook_names_the_ones_that_exist(env):
    ana = env.user("ana@acme.example")
    result = env.call(env.token(ana), "start_run", {"project_id": str(env.project(ana).id), "agent": "content"})
    assert result["isError"] and "insights" in _payload(result)["error"]


def test_the_prompt_returns_the_same_playbook(env, no_model):
    ana = env.user("ana@acme.example")
    project = env.project(ana)
    token = env.token(ana)
    prompt = env.rpc(token, "prompts/get", {"name": "insights_brief", "arguments": {"project_id": str(project.id)}})
    [message] = prompt["result"]["messages"]
    tool = _payload(env.call(token, "start_run", {"project_id": str(project.id)}))
    assert message["role"] == "user" and message["content"]["text"] == tool["playbook"]

    missing = env.rpc(token, "prompts/get", {"name": "insights_brief", "arguments": {}})
    assert missing["error"]["code"] == -32602
    stranger = env.rpc(token, "prompts/get", {"name": "insights_brief", "arguments": {"project_id": str(uuid.uuid4())}})
    assert stranger["error"]["code"] == -32602


def test_initialize_offers_prompts(env):
    ana = env.user("ana@acme.example")
    caps = env.rpc(env.token(ana), "initialize", {"protocolVersion": "2025-11-25"})["result"]["capabilities"]
    assert caps["prompts"] == {"listChanged": False}
    assert json.dumps(caps)
