"""Duct's MCP server: the transport, the token, and the three setup tools.

What these pin, in the order a reviewer would worry about them:

  * an outside agent's write is always a draft: it never replaces what the
    person typed or confirmed, and never outranks their live site;
  * a token reaches only its owner's projects, and a stranger's project reads
    exactly like a made-up id;
  * a token works on /mcp and nowhere else, and a sign-in JWT does not work on
    /mcp;
  * the transport answers the handful of messages a client sends the way the
    spec says, so Claude Code, Codex and Cursor connect at all.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import iter_route_contexts
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

from config import Configs
from db.session import get_session
from models.activity import ActivityLog
from models.auth import McpToken, User
from models.membership import ProjectMember
from models.project import Project
from routes import mcp_server, mcp_tokens
from service.auth import get_current_user
from service.mcp_server.protocol import PROTOCOL_VERSIONS
from service.mcp_tokens import MAX_ACTIVE_TOKENS, TOKEN_PREFIX, mint
from service.membership import ensure_owner_membership
from service.project_draft import PROVENANCE_CRAWL, PROVENANCE_DOCUMENT, PROVENANCE_INFERRED, PROVENANCE_USER
from tests.conftest import make_sqlite_engine
from utils.dates import utcnow


class _Env:
    def __init__(self, session: Session, client: TestClient):
        self.session, self.client = session, client
        self.signed_in: User | None = None

    def user(self, email: str) -> User:
        user = User(email=email, full_name=email.split("@")[0])
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def token(self, user: User, name: str = "Claude Code") -> str:
        return mint(user, name, self.session)[1]

    def project(self, owner: User, **kwargs) -> Project:
        project = Project(user_id=owner.id, name=kwargs.pop("name", "Acme"), slug=f"p-{uuid.uuid4().hex[:8]}", **kwargs)
        self.session.add(project)
        self.session.flush()
        ensure_owner_membership(project, self.session)
        self.session.commit()
        self.session.refresh(project)
        return project

    def rpc(self, token: str | None, method: str, params: dict | None = None, *, id_: int | None = 1, **headers):
        message = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if id_ is not None:
            message["id"] = id_
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post("/mcp", json=message, headers=headers)

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
    app.include_router(mcp_tokens.router, prefix="/api/user/mcp-tokens")
    state = _Env(session, TestClient(app, raise_server_exceptions=False))

    def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state.signed_in
    yield state
    session.close()
    engine.dispose()


# -- the transport -------------------------------------------------------------

def test_initialize_echoes_a_version_the_client_speaks_and_offers_tools(env):
    token = env.token(env.user("ana@acme.example"))
    out = env.rpc(token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "claude-code", "version": "2"}}).json()["result"]
    assert out["protocolVersion"] == "2025-06-18"
    assert out["capabilities"] == {"tools": {"listChanged": False}}
    assert "draft_project" in out["instructions"]

    newer = env.rpc(token, "initialize", {"protocolVersion": "2099-01-01"}).json()["result"]
    assert newer["protocolVersion"] == PROTOCOL_VERSIONS[0], "an unknown version gets our newest"


def test_a_notification_is_acknowledged_with_an_empty_202(env):
    token = env.token(env.user("ana@acme.example"))
    res = env.rpc(token, "notifications/initialized", id_=None)
    assert (res.status_code, res.content) == (202, b"")


def test_the_tool_list_is_the_three_setup_tools_with_flat_schemas(env):
    token = env.token(env.user("ana@acme.example"))
    tools = {t["name"]: t for t in env.rpc(token, "tools/list").json()["result"]["tools"]}
    assert set(tools) == {"list_projects", "get_project", "draft_project"}
    assert tools["get_project"]["annotations"]["readOnlyHint"] is True
    assert tools["draft_project"]["annotations"]["readOnlyHint"] is False
    assert all(t["annotations"]["destructiveHint"] is False for t in tools.values())
    # Several clients resolve no $ref; tool_schema inlines them.
    assert "$ref" not in str(tools["draft_project"]["inputSchema"])
    fields = tools["draft_project"]["inputSchema"]["properties"]["fields"]["properties"]
    assert "SaaS & Software" in fields["industry"]["enum"]
    assert "active_channels" not in fields, "social accounts are left to the site crawl"


@pytest.mark.parametrize(
    "message, code",
    [
        ({"jsonrpc": "2.0", "id": 1, "method": "resources/list"}, -32601),
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "apply_change_set"}}, -32602),
        ([{"jsonrpc": "2.0", "id": 1, "method": "ping"}], -32600),
        ({"id": 1, "method": "ping"}, -32600),
    ],
)
def test_protocol_errors_carry_json_rpc_codes(env, message, code):
    token = env.token(env.user("ana@acme.example"))
    res = env.client.post("/mcp", json=message, headers={"Authorization": f"Bearer {token}"})
    assert res.json()["error"]["code"] == code


def test_a_body_that_is_not_json_is_a_parse_error(env):
    token = env.token(env.user("ana@acme.example"))
    res = env.client.post("/mcp", content=b"{nope", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == -32700


def test_no_event_stream_and_no_unknown_protocol_version(env):
    token = env.token(env.user("ana@acme.example"))
    assert env.client.get("/mcp", headers={"Authorization": f"Bearer {token}"}).status_code == 405
    res = env.rpc(token, "ping", **{"MCP-Protocol-Version": "1999-01-01"})
    assert res.status_code == 400
    assert env.rpc(token, "ping", **{"MCP-Protocol-Version": "2025-06-18"}).json()["result"] == {}


# -- the token -----------------------------------------------------------------

def test_no_token_or_a_foreign_one_is_a_401_with_a_bearer_challenge(env):
    for token in (None, "eyJhbGciOiJIUzI1NiJ9.a-sign-in-jwt.sig", TOKEN_PREFIX + "made-up"):
        res = env.rpc(token, "ping")
        assert res.status_code == 401
        assert res.headers["WWW-Authenticate"].startswith("Bearer")


def test_a_revoked_or_expired_token_stops_working(env):
    ana = env.user("ana@acme.example")
    revoked, expired = env.token(ana, "old laptop"), env.token(ana, "older laptop")
    rows = {r.name: r for r in env.session.execute(select(McpToken)).scalars()}
    rows["old laptop"].revoked_at = utcnow()
    rows["older laptop"].expires_at = utcnow() - timedelta(seconds=1)
    env.session.commit()
    assert env.rpc(revoked, "ping").status_code == 401
    assert env.rpc(expired, "ping").status_code == 401


def test_an_mcp_token_is_not_a_session_for_the_rest_of_the_api(env):
    token = env.token(env.user("ana@acme.example"))
    settings = Configs(jwt_secret="a-test-secret-that-is-long-enough-for-the-check")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(creds, settings, env.session))
    assert exc.value.status_code == 401


def test_the_mounted_mcp_route_resolves_its_caller_from_a_token():
    """The structural half: /mcp is outside /api, so test_route_auth_boundaries
    never looks at it. This does."""
    from server import app

    posts = [c for c in iter_route_contexts(app.routes) if getattr(c, "path", "") == "/mcp" and "POST" in (c.methods or ())]
    assert len(posts) == 1
    names, stack = set(), [posts[0].dependant]
    while stack:
        node = stack.pop()
        names.add(getattr(node.call, "__name__", ""))
        stack.extend(node.dependencies)
    assert "get_mcp_caller" in names
    assert "validate_api_key" not in names and "get_current_user" not in names


# -- the tools -----------------------------------------------------------------

def test_list_projects_shows_only_what_the_person_can_reach(env):
    ana, bo = env.user("ana@acme.example"), env.user("bo@other.example")
    mine = env.project(ana, name="Acme", url="https://acme.example")
    shared = env.project(bo, name="Shared")
    env.session.add(ProjectMember(project_id=shared.id, user_id=ana.id, role="collaborator"))
    env.project(bo, name="Not yours")
    env.session.commit()

    out = env.call(env.token(ana), "list_projects")["structuredContent"]
    assert out["signed_in_as"] == "ana@acme.example"
    by_name = {p["name"]: p for p in out["projects"]}
    assert set(by_name) == {"Acme", "Shared"}
    assert (by_name["Acme"]["role"], by_name["Shared"]["role"]) == ("owner", "collaborator")
    assert by_name["Acme"]["review_url"].endswith(f"/project/{mine.id}")


def test_a_strangers_project_reads_exactly_like_a_made_up_one(env):
    ana, bo = env.user("ana@acme.example"), env.user("bo@other.example")
    theirs = env.project(bo, name="Not yours", pitch="secret")
    token = env.token(ana)
    stranger = env.call(token, "get_project", {"project_id": str(theirs.id)})
    made_up = env.call(token, "get_project", {"project_id": str(uuid.uuid4())})
    assert stranger["isError"] and made_up["isError"]
    assert stranger["structuredContent"] == made_up["structuredContent"]
    assert "secret" not in str(stranger)

    drafted = env.call(token, "draft_project", {"project_id": str(theirs.id), "fields": {"pitch": "Mine now"}})
    assert drafted["isError"]
    env.session.refresh(theirs)
    assert theirs.pitch == "secret"


def test_get_project_says_where_each_value_came_from(env):
    ana = env.user("ana@acme.example")
    project = env.project(ana, pitch="Typed long ago", industry="SaaS & Software",
                          provenance={"industry": PROVENANCE_CRAWL})
    fields = env.call(env.token(ana), "get_project", {"project_id": str(project.id)})["structuredContent"]["fields"]
    assert fields["pitch"] == {"value": "Typed long ago", "source": "set by the person"}
    assert fields["industry"]["source"] == "from their website"
    assert fields["brand_voice"] == {"value": None, "source": None}


def test_a_draft_creates_a_project_labelled_as_files_and_guesses(env):
    ana = env.user("ana@acme.example")
    out = env.call(env.token(ana, "Claude Code on the laptop"), "draft_project", {
        "fields": {
            "name": "Maxaura", "pitch": "AI photo studio for small shops.",
            "website_url": "https://maxauralab.com", "industry": "SaaS & Software",
            "personas": [{"name": "Shop owner", "description": "Needs product shots without a studio."},
                         {"name": "Agency"}],
        },
        "guessed": ["industry"],
    })
    assert not out["isError"], out
    result = out["structuredContent"]
    assert result["created"] is True and result["kept"] == []
    project = env.session.get(Project, uuid.UUID(result["project_id"]))
    assert (project.name, project.url, project.slug) == ("Maxaura", "https://maxauralab.com", "maxaura")
    assert project.provenance["pitch"] == PROVENANCE_DOCUMENT
    assert project.provenance["industry"] == PROVENANCE_INFERRED
    assert [p["priority"] for p in project.audience["personas"]] == ["primary", "secondary"]
    assert env.session.execute(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == ana.id)
    ).scalars().first().role == "owner"

    log = env.session.execute(select(ActivityLog).where(ActivityLog.project_id == project.id)).scalars().one()
    assert (log.category, log.action, log.source) == ("project", "project.created", "agent")
    assert "Claude Code on the laptop" in log.summary


def test_a_draft_never_replaces_the_person_or_their_site(env):
    ana = env.user("ana@acme.example")
    project = env.project(
        ana, name="Acme", pitch="What I typed", industry="Education", company_name="Acme Inc",
        url="https://acme.example",
        provenance={"pitch": PROVENANCE_USER, "industry": PROVENANCE_CRAWL, "company_name": PROVENANCE_DOCUMENT},
    )
    out = env.call(env.token(ana), "draft_project", {
        "project_id": str(project.id),
        "fields": {"name": "Acme 2", "pitch": "From the README", "industry": "SaaS & Software",
                   "company_name": "Acme Labs", "brand_voice": "Technical"},
    })["structuredContent"]
    assert sorted(out["changed"]) == ["brand_voice", "company_name"]
    reasons = {k["field"]: k["reason"] for k in out["kept"]}
    assert "never replaces" in reasons["pitch"]
    assert "never replaces" in reasons["name"], "unlabelled and filled means the person typed it"
    assert "website" in reasons["industry"]
    env.session.refresh(project)
    assert (project.name, project.pitch, project.industry) == ("Acme", "What I typed", "Education")
    assert project.company_name == "Acme Labs"


def test_running_the_same_draft_again_changes_nothing(env):
    ana = env.user("ana@acme.example")
    token = env.token(ana)
    first = env.call(token, "draft_project", {"fields": {"name": "Acme", "pitch": "Dinners, planned."}})
    project_id = first["structuredContent"]["project_id"]
    stamp = env.session.get(Project, uuid.UUID(project_id)).updated_at
    again = env.call(token, "draft_project", {"project_id": project_id,
                                              "fields": {"name": "Acme", "pitch": "Dinners, planned."}})
    assert again["structuredContent"]["changed"] == []
    assert {k["reason"] for k in again["structuredContent"]["kept"]} == {"already up to date"}
    env.session.expire_all()
    assert env.session.get(Project, uuid.UUID(project_id)).updated_at == stamp
    assert env.session.execute(select(ActivityLog)).scalars().all().__len__() == 1


def test_creating_a_second_project_for_the_same_site_is_refused(env):
    ana = env.user("ana@acme.example")
    existing = env.project(ana, url="https://www.acme.example/")
    out = env.call(env.token(ana), "draft_project", {"fields": {"name": "Acme", "website_url": "https://acme.example"}})
    assert out["isError"]
    assert str(existing.id) in out["structuredContent"]["error"]


@pytest.mark.parametrize("arguments", [
    {"fields": {"industry": "Beauty tech"}},
    {"fields": {"north_star_metric": "Revenue"}},
    {"fields": {"website_url": "javascript:alert(1)"}},
    {"fields": {"name": "Acme"}, "guessed": ["autonomy_level"]},
    {"fields": {}},
])
def test_a_bad_draft_is_an_error_the_model_can_read_and_writes_nothing(env, arguments):
    ana = env.user("ana@acme.example")
    out = env.call(env.token(ana), "draft_project", arguments)
    assert out["isError"]
    assert out["structuredContent"]["error"]
    assert env.session.execute(select(Project)).scalars().all() == []


# -- the token routes ------------------------------------------------------------

def test_a_token_is_shown_once_listed_by_hint_and_revocable(env):
    env.signed_in = env.user("ana@acme.example")
    made = env.client.post("/api/user/mcp-tokens", json={"name": "Claude Code"})
    assert made.status_code == 201, made.text
    raw = made.json()["token"]
    assert raw.startswith(TOKEN_PREFIX)

    listed = env.client.get("/api/user/mcp-tokens").json()
    assert [(t["name"], t["hint"]) for t in listed] == [("Claude Code", raw[-4:])]
    assert "token" not in listed[0] and raw not in str(listed)
    assert env.session.execute(select(McpToken.token_hash)).scalar_one() != raw

    assert env.rpc(raw, "ping").status_code == 200
    assert env.client.delete(f"/api/user/mcp-tokens/{listed[0]['id']}").status_code == 204
    assert env.rpc(raw, "ping").status_code == 401
    assert env.client.get("/api/user/mcp-tokens").json() == []


def test_someone_elses_token_cannot_be_revoked_and_the_count_is_capped(env):
    ana, bo = env.user("ana@acme.example"), env.user("bo@other.example")
    env.token(bo)
    theirs = env.session.execute(select(McpToken).where(McpToken.user_id == bo.id)).scalar_one()
    env.signed_in = ana
    assert env.client.delete(f"/api/user/mcp-tokens/{theirs.id}").status_code == 404
    assert env.client.post("/api/user/mcp-tokens", json={"name": "  "}).status_code == 422

    for i in range(MAX_ACTIVE_TOKENS):
        assert env.client.post("/api/user/mcp-tokens", json={"name": f"agent {i}"}).status_code == 201
    assert env.client.post("/api/user/mcp-tokens", json={"name": "one more"}).status_code == 409
