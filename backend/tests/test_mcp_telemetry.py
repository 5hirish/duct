"""What the MCP server reports about its own calls, and what it never does.

Pinned, in the order they would hurt:

  * a call's arguments and results never reach analytics, and the model's
    stated reason is redacted before it does;
  * a broken analytics client never changes a reply;
  * every tool call is one ``$mcp_tool_call`` in PostHog's MCP Analytics
    shape, with failures sorted into a few classes rather than messages;
  * ``initialize`` hands out a session label the next calls are grouped by,
    and the reason argument never reaches a tool's strict argument model.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from db.session import get_session
from models.auth import User
from models.project import Project
from routes import mcp_server
from service import analytics
from service.mcp_server import telemetry, tools
from service.mcp_server.protocol import CONTEXT_ARG
from service.mcp_tokens import mint
from service.membership import ensure_owner_membership
from tests.conftest import make_sqlite_engine


class _FakePostHog:
    def __init__(self, *, broken: bool = False):
        self.events: list[dict] = []
        self.broken = broken

    def capture(self, event, **kwargs):
        if self.broken:
            raise RuntimeError("analytics is down")
        self.events.append({"event": event, **kwargs})

    def set(self, **_):
        pass

    def named(self, event: str) -> list[dict]:
        return [e for e in self.events if e["event"] == event]


@pytest.fixture
def posthog(monkeypatch):
    fake = _FakePostHog()
    monkeypatch.setattr(analytics, "_client", fake)
    monkeypatch.setattr(analytics, "_client_built", True)
    monkeypatch.setattr(analytics, "_identified", {})
    return fake


@pytest.fixture
def mcp():
    engine = make_sqlite_engine(drop_partial_indexes=True)
    session = Session(engine)
    app = FastAPI()
    app.include_router(mcp_server.router)

    def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    client = TestClient(app, raise_server_exceptions=False)
    user = User(email="ana@acme.example", full_name="Ana")
    session.add(user)
    session.commit()
    session.refresh(user)
    project = Project(user_id=user.id, name="Acme", slug=f"p-{uuid.uuid4().hex[:8]}")
    session.add(project)
    session.flush()
    ensure_owner_membership(project, session)
    session.commit()
    token = mint(user, "Claude Code", session)[1]

    def rpc(method, params=None, **headers):
        headers.setdefault("Authorization", f"Bearer {token}")
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        return client.post("/mcp", json=body, headers=headers)

    rpc.user, rpc.project = user, project
    yield rpc
    session.close()
    engine.dispose()


def _call(mcp, tool, arguments=None, **headers):
    return mcp("tools/call", {"name": tool, "arguments": arguments or {}}, **headers)


def test_a_call_is_one_tool_call_event_in_posthogs_mcp_shape(mcp, posthog):
    res = _call(mcp, "get_project", {"project_id": str(mcp.project.id)}, **{"User-Agent": "claude-code/9.9"})
    assert res.json()["result"]["isError"] is False
    [event] = posthog.named("$mcp_tool_call")
    props = event["properties"]
    assert event["distinct_id"] == str(mcp.user.id)
    assert props["$mcp_source"] == "posthog_mcp_analytics"
    assert props["$mcp_server_name"] == "duct"
    assert props["$mcp_tool_name"] == "get_project"
    assert props["$mcp_is_error"] is False, "a JSON boolean, which the dashboards filter on"
    assert isinstance(props["$mcp_duration_ms"], float)
    assert props["$session_id"].startswith("ses_")
    assert props["$mcp_client_user_agent"] == "claude-code/9.9"
    assert props["project_id"] == str(mcp.project.id)
    assert props["token_kind"] == "token"
    assert props["result_chars"] > 0
    assert event["timestamp"] is not None


def test_arguments_and_results_never_leave(mcp, posthog):
    _call(mcp, "draft_project", {"project_id": str(mcp.project.id), "fields": {"pitch": "Secret roadmap pitch"}})
    sent = str(posthog.events)
    assert "$mcp_parameters" not in sent and "$mcp_response" not in sent
    assert "Secret roadmap pitch" not in sent


def test_failures_are_counted_by_class_not_by_message(mcp, posthog):
    _call(mcp, "get_project", {"project_id": "not-a-uuid"})
    _call(mcp, "get_project", {"project_id": str(uuid.uuid4())})
    validation, not_found = posthog.named("$mcp_tool_call")
    assert (validation["properties"]["$mcp_is_error"], validation["properties"]["$mcp_error_type"]) == (
        True,
        "validation",
    )
    assert not_found["properties"]["$mcp_error_type"] == "not_found"
    assert not_found["properties"]["$mcp_error_message"], "PostHog's spec keeps the (redacted) message"


def test_an_exception_is_an_internal_error_event_and_still_an_error_reply(mcp, posthog, monkeypatch):
    def explode(args, caller):
        raise RuntimeError("database fell over")

    tool = tools.TOOLS["list_projects"]
    monkeypatch.setitem(tools.TOOLS, "list_projects", tool.__class__(**{**tool.__dict__, "run": explode}))
    res = _call(mcp, "list_projects")
    assert res.json()["error"]["code"] == -32603
    [event] = posthog.named("$mcp_tool_call")
    assert event["properties"]["$mcp_error_type"] == "internal"
    assert event["properties"]["$mcp_error_message"] == "RuntimeError", "the class, never the text"


def test_an_unknown_tool_is_not_a_tool_call(mcp, posthog):
    _call(mcp, "apply_change_set")
    assert posthog.named("$mcp_tool_call") == []


def test_the_reason_argument_is_optional_stripped_and_redacted(mcp, posthog):
    listed = mcp("tools/list").json()["result"]["tools"]
    for tool in listed:
        assert CONTEXT_ARG in tool["inputSchema"]["properties"]
        assert CONTEXT_ARG not in tool["inputSchema"].get("required", [])
    # list_projects' arguments forbid anything extra, so this succeeding
    # means the reason was taken out before validation.
    res = _call(mcp, "list_projects", {CONTEXT_ARG: "Founder ana@acme.example wants to refresh the pitch"})
    assert res.json()["result"]["isError"] is False
    props = posthog.named("$mcp_tool_call")[0]["properties"]
    assert props["$mcp_intent"] == "Founder [email] wants to refresh the pitch"
    assert props["$mcp_intent_source"] == "context_parameter"


def test_initialize_hands_out_a_session_label_later_calls_share(mcp, posthog):
    res = mcp("initialize", {"protocolVersion": "2025-11-25", "clientInfo": {"name": "claude-code", "version": "9.9"}})
    session_id = res.headers[telemetry.SESSION_HEADER]
    [init] = posthog.named("$mcp_initialize")
    assert (init["properties"]["$mcp_client_name"], init["properties"]["$mcp_client_version"]) == ("claude-code", "9.9")
    assert session_id not in str(posthog.events), "sent hashed, never as the client holds it"

    _call(mcp, "list_projects", **{telemetry.SESSION_HEADER: session_id})
    _call(mcp, "list_projects", **{telemetry.SESSION_HEADER: session_id})
    _call(mcp, "list_projects")
    first, second, loose = (e["properties"]["$session_id"] for e in posthog.named("$mcp_tool_call"))
    assert first == second == init["properties"]["$session_id"]
    assert loose != first, "no header is a fresh label, never someone else's session"


def test_a_broken_analytics_client_changes_no_reply(mcp, monkeypatch):
    monkeypatch.setattr(analytics, "_client", _FakePostHog(broken=True))
    monkeypatch.setattr(analytics, "_client_built", True)
    res = _call(mcp, "list_projects")
    assert res.status_code == 200 and res.json()["result"]["isError"] is False


def test_a_failed_credential_is_counted_and_a_missing_one_is_not(mcp, posthog):
    assert mcp("tools/list", Authorization="").status_code == 401
    assert posthog.events == [], "a first call with no token is OAuth discovery, not a refusal"
    assert mcp("tools/list", Authorization="Bearer duct_mcp_nope").status_code == 401
    [refused] = posthog.named("mcp_request_refused")
    assert refused["properties"]["reason"] == "invalid_token"
    assert refused["properties"]["$process_person_profile"] is False
    assert "duct_mcp_nope" not in str(posthog.events)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("token=abc123 and Bearer xyz", "token=[redacted] and Bearer [redacted]"),
        ("call +1 415 555 0134 tomorrow", "call [number] tomorrow"),
        ("plan for 2026-11-24", "plan for 2026-11-24"),
        ("https://u:pw@example.com/x", "https://[redacted]@example.com/x"),
        ("key duct_mcp_AbC123_xyz leaked", "key [redacted] leaked"),
    ],
)
def test_redaction(text, expected):
    assert telemetry.redact(text) == expected


@pytest.mark.parametrize(
    "hostile",
    ["a" * 256_000, "a." * 128_000, "://" + "a:" * 128_000, "Bearer " + " " * 256_000, "x@" + "y" * 256_000],
)
def test_redaction_is_linear_on_a_models_longest_text(hostile):
    # The reason text is the calling model's and as long as a request body
    # allows. An unbounded pattern here backtracked quadratically: 32,000
    # characters took over five seconds of a worker (CodeQL py/polynomial-redos).
    import time

    started = time.perf_counter()
    out = telemetry.redact(hostile)
    assert time.perf_counter() - started < 0.5
    assert len(out) <= 2048


def test_the_reason_is_cut_where_the_protocol_reads_it(mcp, posthog):
    _call(mcp, "list_projects", {CONTEXT_ARG: "why " * 5_000})
    props = posthog.named("$mcp_tool_call")[0]["properties"]
    assert len(props["$mcp_intent"]) <= 2048
