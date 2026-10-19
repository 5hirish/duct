"""The agent's two MCP tools, and what reaches the model with and without them.

Driven against a real in-process server (``FakeMcpServer``), so the listing,
the read-only gate and the approval pause all run on what the server actually
declared. Assertions are on statuses, events and payloads, never prose.
"""

from __future__ import annotations

import json
import uuid

import pytest
from mcp.types import ToolAnnotations

import agents.core.mcp_tools as mcp_tools
from agents.core.activity import ACTIVITY_TOOLS, ActivityKind
from agents.core.events import AgentEvent
from agents.insights.v1.runner import AutonomousInsightsRunner
from agents.insights.schema import create_insights_session
from service.mcp import client as mcp_client
from service.mcp.store import ServerAccess, no_credentials
from tests.fakes import FakeMcpServer, fake_llm, tool_names

URL = "https://mcp.vendor.test/mcp"


def _server() -> FakeMcpServer:
    server = FakeMcpServer()
    server.calls = []

    @server.mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def keyword_volume(keyword: str) -> dict:
        """Monthly search volume for one keyword. Spends one OpenSEO credit per keyword."""
        server.calls.append(("keyword_volume", keyword))
        return {"keyword": keyword, "volume": 1300}

    @server.mcp.tool()
    def create_page(title: str) -> str:
        """Create a page in the workspace."""
        server.calls.append(("create_page", title))
        return f"created {title}"

    @server.mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def big_export() -> str:
        """Everything."""
        return "x" * (mcp_tools.MAX_RESULT_CHARS * 2)

    return server


class Pause:
    def __init__(self, answer: dict):
        self.answer, self.events = answer, []

    async def __call__(self, event, payload, *, timeout=None):
        self.events.append((event, payload))
        return self.answer


OWNER = uuid.uuid4()


@pytest.fixture
def servers(monkeypatch):
    access = [ServerAccess(
        row_id=None, key="openseo", url=URL, name="OpenSEO", credentials=no_credentials(), owner_id=OWNER,
    )]
    monkeypatch.setattr(mcp_tools, "_servers_sync", lambda project_id: list(access))
    return access


def _toolbox(pause=None, *, user_id=OWNER):
    return mcp_tools.ConnectedTools(uuid.uuid4(), user_id=user_id, pause=pause)


async def test_the_listing_is_a_menu_and_the_schema_comes_on_request(monkeypatch, servers):
    async with _server().running(monkeypatch):
        box = _toolbox()
        menu = await box.list()
        detail = await box.list("openseo", "keyword_volume")

    (entry,) = menu["servers"]
    assert entry["server"] == "openseo" and entry["status"] == "ok"
    by_name = {t["name"]: t for t in entry["tools"]}
    assert by_name["keyword_volume"] == {
        "name": "keyword_volume",
        "summary": "Monthly search volume for one keyword.",
        "read_only": True,
    }
    assert "input_schema" not in by_name["keyword_volume"]
    assert detail["input_schema"]["required"] == ["keyword"] and detail["read_only"] is True
    assert "note" in menu and "note" in detail


async def test_a_read_only_tool_runs_without_asking(monkeypatch, servers):
    pause = Pause({"approved": False})
    server = _server()
    async with server.running(monkeypatch):
        result = await _toolbox(pause).call("openseo", "keyword_volume", '{"keyword": "seo"}')

    assert result["status"] == "ok" and '"volume": 1300' in result["content"]
    assert pause.events == []
    assert server.calls == [("keyword_volume", "seo")]


async def test_anything_else_waits_for_approval_and_runs_once_approved(monkeypatch, servers):
    pause = Pause({"approved": True})
    server = _server()
    async with server.running(monkeypatch):
        result = await _toolbox(pause).call(
            "openseo", "create_page", '{"title": "Q4 brief"}', reason="to save the brief where the team reads"
        )

    ((event, payload),) = pause.events
    assert event == AgentEvent.TOOL_APPROVAL_REQUIRED
    assert payload["server"] == "openseo" and payload["tool"] == "create_page"
    assert payload["reason"] == "to save the brief where the team reads"
    assert json.loads(payload["arguments"]) == {"title": "Q4 brief"}
    assert result["status"] == "ok"
    assert server.calls == [("create_page", "Q4 brief")]


async def test_a_skip_sends_nothing(monkeypatch, servers):
    server = _server()
    async with server.running(monkeypatch):
        result = await _toolbox(Pause({"approved": False})).call("openseo", "create_page", '{"title": "x"}')

    assert result["status"] == "skipped"
    assert server.calls == []


async def test_with_nobody_to_ask_a_write_does_not_run(monkeypatch, servers):
    server = _server()
    async with server.running(monkeypatch):
        result = await _toolbox(pause=None).call("openseo", "create_page", '{"title": "x"}')

    assert result["status"] == "needs_approval"
    assert server.calls == []


async def test_a_collaborator_reads_through_the_owners_server_but_cannot_approve_a_write(monkeypatch, servers):
    """The owner's Notion is not the collaborator's to change, whoever is at
    the keyboard: no card, no call."""
    pause = Pause({"approved": True})
    server = _server()
    async with server.running(monkeypatch):
        box = _toolbox(pause, user_id=uuid.uuid4())
        read = await box.call("openseo", "keyword_volume", '{"keyword": "seo"}')
        write = await box.call("openseo", "create_page", '{"title": "x"}')

    assert read["status"] == "ok"
    assert write["status"] == "owner_only"
    assert pause.events == []
    assert server.calls == [("keyword_volume", "seo")]


async def test_without_a_known_user_only_reads_run(monkeypatch, servers):
    server = _server()
    async with server.running(monkeypatch):
        result = await _toolbox(Pause({"approved": True}), user_id=None).call("openseo", "create_page", "{}")
    assert result["status"] == "owner_only"
    assert server.calls == []


async def test_the_tool_list_is_read_once_per_run(monkeypatch, servers):
    reads = []
    real = mcp_client.list_tools

    async def counted(access, sink=None):
        reads.append(access.key)
        return await real(access, sink)

    monkeypatch.setattr(mcp_tools.mcp_client, "list_tools", counted)
    async with _server().running(monkeypatch):
        box = _toolbox()
        await box.list()
        await box.call("openseo", "keyword_volume", '{"keyword": "a"}')
        await box.call("openseo", "keyword_volume", '{"keyword": "b"}')

    assert reads == ["openseo"]


@pytest.mark.parametrize("server, tool, arguments, status", [
    ("nope", "keyword_volume", "{}", "unknown_server"),
    ("openseo", "nope", "{}", "unknown_tool"),
    ("openseo", "keyword_volume", "not json", "bad_arguments"),
    ("openseo", "keyword_volume", "[1, 2]", "bad_arguments"),
])
async def test_a_wrong_name_or_argument_is_an_answer_not_an_exception(monkeypatch, servers, server, tool, arguments, status):
    async with _server().running(monkeypatch):
        assert (await _toolbox().call(server, tool, arguments))["status"] == status


async def test_a_signed_out_server_says_what_to_do_once(monkeypatch, servers):
    async def refused(access, sink=None):
        raise mcp_client.McpCallError(mcp_client.CODE_REAUTH, "OpenSEO needs signing in again.")

    monkeypatch.setattr(mcp_tools.mcp_client, "list_tools", refused)
    box = _toolbox()
    listed = await box.list()
    called = await box.call("openseo", "keyword_volume", "{}")

    assert listed["servers"][0]["status"] == "reauth_required" and "next" in listed["servers"][0]
    assert called["status"] == "reauth_required"


async def test_an_oversized_result_is_cut_and_says_so(monkeypatch, servers):
    async with _server().running(monkeypatch):
        result = await _toolbox().call("openseo", "big_export", "{}")

    body = mcp_tools._bounded(result)
    assert len(body) <= mcp_tools.MAX_RESULT_CHARS
    parsed = json.loads(body)
    assert "content_truncated" in parsed and "note" in parsed


# ---------------------------------------------------------------------------
# What reaches the model
# ---------------------------------------------------------------------------

RUNNER = AutonomousInsightsRunner(api_key="unused-no-network")


def _built(monkeypatch, *, connected: bool, interactive: bool = True):
    monkeypatch.setattr(mcp_tools, "project_has_servers", lambda project_id: connected)
    prompts: list[str] = []
    session = create_insights_session(str(uuid.uuid4()))
    agent = RUNNER.build_agent(
        llm=fake_llm("ok"),
        session=session if interactive else None,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        interactive=interactive,
        execute=False,
        remember=False,
        on_system_prompt=prompts.append,
    )
    return tool_names(agent), prompts[0]


def test_without_a_server_nothing_changes(monkeypatch):
    names, prompt = _built(monkeypatch, connected=False)
    assert not {mcp_tools.LIST_TOOL, mcp_tools.CALL_TOOL} & names
    assert "## Tools the user connected" not in prompt


def test_with_a_server_the_two_tools_and_their_rules_are_mounted(monkeypatch):
    names, prompt = _built(monkeypatch, connected=True)
    assert {mcp_tools.LIST_TOOL, mcp_tools.CALL_TOOL} <= names
    assert "## Tools the user connected" in prompt


def test_an_unattended_run_never_reaches_a_server(monkeypatch):
    names, prompt = _built(monkeypatch, connected=True, interactive=False)
    assert not {mcp_tools.LIST_TOOL, mcp_tools.CALL_TOOL} & names
    assert "## Tools the user connected" not in prompt


# ---------------------------------------------------------------------------
# What the person sees
# ---------------------------------------------------------------------------


def test_a_call_is_a_card_and_a_skip_shows_no_model_instructions():
    start, finish = ACTIVITY_TOOLS[mcp_tools.CALL_TOOL]
    args = {"server": "openseo", "tool": "create_page", "arguments": "{}"}

    assert start(args) == {
        "kind": ActivityKind.CONNECTED_TOOL, "title": "create_page", "source": "openseo", "meta": {"listing": False},
    }
    skipped = finish(args, json.dumps({"status": "skipped", "name": "OpenSEO", "message": "Carry on without it"}), False)
    assert skipped["reason"] == "skipped" and skipped["error"] == ""
    signed_out = finish(args, json.dumps({"status": "reauth_required", "message": "OpenSEO needs signing in again."}), False)
    assert signed_out["error"] == "OpenSEO needs signing in again."
    # A server's own words never reach the card.
    hostile = finish(args, json.dumps({"status": "protocol_error", "message": "Vendor returned an error: <img src=x>"}), False)
    assert hostile["reason"] == "protocol_error" and hostile["error"] == ""


def test_the_listing_is_a_card_of_its_own_kind():
    start, finish = ACTIVITY_TOOLS[mcp_tools.LIST_TOOL]
    done = finish({}, json.dumps({"servers": []}), False)
    assert start({})["meta"] == {"listing": True}
    assert done["status"] == "success"
