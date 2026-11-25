"""What a connection may do and where: the two tiers and per-project grants.

Pinned, in the order they would hurt:

  * a connection reaches only the projects the person chose, and a project
    outside the grant reads exactly like one that does not exist;
  * a tool outside the granted scopes is absent from the list and refused
    if called by name anyway;
  * a row made before scopes existed keeps exactly what it had: project setup;
  * the person, not the agent, decides: what an agent asks for never becomes
    a grant by itself, and a grant naming someone else's project is refused
    without spending the sign-in request;
  * the incident switch hides every write at once;
  * no tool anywhere approves, applies or publishes.
"""

# The sign-in module's fixtures are imported and injected by name, which
# Ruff reads as a parameter shadowing an import.
# ruff: noqa: F811

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from config import Configs
from models.auth import McpToken
from models.project import Project
from service.mcp_server import protocol, scopes
from service.mcp_server.tools import TOOLS
from service.mcp_tokens import mint
from service.membership import ensure_owner_membership
from tests.test_mcp_server_signin import (  # noqa: F401 — the shared sign-in fixtures
    API,
    APP,
    SECRET,
    _pkce,
    _query,
    config,
    env,
)


def _project(env, owner, name: str) -> Project:
    project = Project(user_id=owner.id, name=name, slug=f"p-{uuid.uuid4().hex[:8]}")
    env.session.add(project)
    env.session.flush()
    ensure_owner_membership(project, env.session)
    env.session.commit()
    env.session.refresh(project)
    return project


def _rpc(env, token: str, method: str, params: dict | None = None) -> dict:
    res = env.client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _listed(env, token: str) -> set[str]:
    return {t["name"] for t in _rpc(env, token, "tools/list")["result"]["tools"]}


def _call(env, token: str, tool: str, arguments: dict | None = None) -> dict:
    return _rpc(env, token, "tools/call", {"name": tool, "arguments": arguments or {}})["result"]


def _names(scope: str) -> set[str]:
    return {name for name, tool in TOOLS.items() if tool.scope == scope}


def _sign_in_with(env, user, answer: dict | None):
    """The browser flow with the person's choices on the consent page."""
    env.signed_in = user
    client_id = env.register("Claude Code")
    verifier, challenge = _pkce()
    request_code = env.consent(client_id, challenge)
    res = env.client.post(f"/api/oauth/requests/{request_code}/approve", json=answer)
    assert res.status_code == 200, res.text
    code = _query(res.json()["redirect_to"])["code"]
    tokens = env.exchange(client_id, code, verifier)
    assert tokens.status_code == 200, tokens.text
    return client_id, tokens.json()


# -- the registry ------------------------------------------------------------------

def test_every_tool_names_a_known_scope_and_none_approves_applies_or_publishes():
    assert TOOLS, "the registry is empty"
    for name, tool in TOOLS.items():
        assert tool.scope in scopes.ALL_SCOPES, name
        assert not any(word in name for word in ("approve", "apply", "publish")), name


def test_scope_words_parse_the_way_the_server_stores_them():
    assert scopes.parse(None) == {"projects"}
    assert scopes.parse("mcp") == {"projects"}, "the one scope before tiers"
    assert scopes.parse("data nonsense reports") == {"projects", "data", "reports"}
    assert scopes.serialize({"reports", "projects", "data"}) == "projects data reports"


# -- legacy rows ---------------------------------------------------------------------

def test_a_row_from_before_scopes_keeps_project_setup_and_nothing_more(env):
    user = env.user("ana@acme.example")
    row, raw = mint(user, "Old laptop", env.session)
    row.scopes = None
    env.session.add(row)
    env.session.commit()
    assert _listed(env, raw) == _names("projects")


# -- the consent page --------------------------------------------------------------

def test_what_the_agent_asks_for_is_a_suggestion_the_page_shows(env):
    env.signed_in = env.user("ana@acme.example")
    _, challenge = _pkce()
    request_code = env.consent(env.register(), challenge, scope="projects data media made-up")
    described = env.client.get(f"/api/oauth/requests/{request_code}").json()
    assert described["requested_scopes"] == ["data", "media", "projects"]


def test_allow_with_no_choices_is_project_setup_on_every_project(env):
    user = env.user("ana@acme.example")
    _, tokens = _sign_in_with(env, user, None)
    assert tokens["scope"] == "projects"
    assert _listed(env, tokens["access_token"]) == _names("projects")


def test_the_person_grants_capabilities_on_chosen_projects(env):
    user = env.user("ana@acme.example")
    chosen, other = _project(env, user, "Client A"), _project(env, user, "Client B")
    _, tokens = _sign_in_with(env, user, {"scopes": ["projects", "data", "reports"], "project_ids": [str(chosen.id)]})
    token = tokens["access_token"]
    assert tokens["scope"] == "projects data reports", "the response names what the person allowed"
    assert _listed(env, token) == _names("projects") | _names("data") | _names("reports")

    listed = _call(env, token, "list_projects")["structuredContent"]["projects"]
    assert [p["project_id"] for p in listed] == [str(chosen.id)]
    outside = _call(env, token, "get_project", {"project_id": str(other.id)})
    made_up = _call(env, token, "get_project", {"project_id": str(uuid.uuid4())})
    assert outside["isError"] and outside["structuredContent"] == made_up["structuredContent"]


def test_a_renewal_keeps_what_the_person_allowed(env):
    user = env.user("ana@acme.example")
    chosen = _project(env, user, "Client A")
    client_id, tokens = _sign_in_with(env, user, {"scopes": ["projects", "memory"], "project_ids": [str(chosen.id)]})
    renewed = env.refresh(client_id, tokens["refresh_token"]).json()
    assert renewed["scope"] == "projects memory"
    row = env.session.query(McpToken).filter(McpToken.client_id == client_id).one()
    assert row.project_ids == [str(chosen.id)]


def test_a_grant_naming_someone_elses_project_is_refused_and_the_request_survives(env):
    stranger = env.user("eve@else.example")
    theirs = _project(env, stranger, "Not yours")
    user = env.user("ana@acme.example")
    env.signed_in = user
    client_id = env.register()
    verifier, challenge = _pkce()
    request_code = env.consent(client_id, challenge)

    url = f"/api/oauth/requests/{request_code}/approve"
    refused = env.client.post(url, json={"scopes": ["projects"], "project_ids": [str(theirs.id)]})
    assert refused.status_code == 422
    assert env.client.post(url, json={"scopes": ["projects"], "project_ids": []}).status_code == 422
    # Fixing the selection and pressing Allow again works: nothing was spent.
    assert env.client.post(url, json={"scopes": ["projects"]}).status_code == 200


# -- calls outside the grant ------------------------------------------------------------

def test_a_tool_outside_the_grant_is_refused_when_called_by_name(env):
    user = env.user("ana@acme.example")
    _, raw = mint(user, "Setup only", env.session)
    outside = sorted(set(TOOLS) - _names("projects"))
    if not outside:
        pytest.skip("no tool outside project setup is registered yet")
    result = _call(env, raw, outside[0], {})
    assert result["isError"] is True
    assert "not allowed on this connection" in result["structuredContent"]["error"]


def test_a_connection_limited_to_some_projects_cannot_create_one(env):
    user = env.user("ana@acme.example")
    chosen = _project(env, user, "Client A")
    _, raw = mint(user, "One client", env.session, project_ids=[chosen.id])
    result = _call(env, raw, "draft_project", {"fields": {"name": "Brand new", "website_url": "https://new.example"}})
    assert result["isError"] is True
    assert "cannot create one" in result["structuredContent"]["error"]


# -- personal tokens --------------------------------------------------------------------

def test_a_personal_token_carries_the_same_choices(env):
    user = env.user("ana@acme.example")
    env.signed_in = user
    chosen = _project(env, user, "Client A")
    res = env.client.post(
        "/api/user/mcp-tokens",
        json={"name": "CI", "scopes": ["projects", "data"], "project_ids": [str(chosen.id)]},
    )
    assert res.status_code == 201, res.text
    minted = res.json()
    assert (minted["scopes"], minted["project_ids"]) == (["projects", "data"], [str(chosen.id)])
    assert _listed(env, minted["token"]) == _names("projects") | _names("data")

    stranger_project = _project(env, env.user("eve@else.example"), "Not yours")
    refused = env.client.post(
        "/api/user/mcp-tokens", json={"name": "Sneaky", "project_ids": [str(stranger_project.id)]}
    )
    assert refused.status_code == 422


# -- the incident switch ------------------------------------------------------------------

def test_switching_writes_off_hides_every_write_and_keeps_every_read(env, monkeypatch):
    user = env.user("ana@acme.example")
    _, raw = mint(user, "Everything", env.session, scopes=scopes.ALL_SCOPES)
    off = Configs(api_public_url=API, frontend_origin=APP, jwt_secret=SECRET, mcp_write_tools_enabled=False)
    monkeypatch.setattr(protocol, "get_configs", lambda: off)
    listed = _listed(env, raw)
    assert listed == {name for name, tool in TOOLS.items() if tool.read_only}
    assert _call(env, raw, "update_project", {"project_id": str(uuid.uuid4()), "fields": {}})["isError"]


def test_a_caller_reads_its_grant_off_the_row():
    caller = protocol.Caller(
        user=SimpleNamespace(), token=SimpleNamespace(scopes="projects data", project_ids=["a"]), session=None
    )
    assert caller.scopes == {"projects", "data"}
    assert caller.allows_project("a") and not caller.allows_project("b")
    everywhere = protocol.Caller(user=None, token=SimpleNamespace(scopes=None, project_ids=None), session=None)
    assert everywhere.allows_project("anything")
