"""Harness contract tests for the deepagents/LangGraph migration.

These pin the primitives the audit and content ports depend on — the ones the
Claude Agent SDK provides today via `AskUserQuestion`, `can_use_tool` and the
SSE pump (the engine consolidation review (duct-cloud, private) §6.5, §9.6):

  * a tool call pauses for human review *before* the tool runs
  * the interrupt payload is serialisable, so it can cross our SSE stream
  * approving resumes and runs the tool; rejecting does not
  * token-level and state-level streaming both work while resuming

A fake chat model drives them so the harness is under test, not a provider —
these must stay green with no API key and no network.

If these break on a dependency bump, the migration's foundation moved: read the
failure before changing the assertions.
"""

from __future__ import annotations

import json
import uuid

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from deepagents import create_deep_agent
from agents.core.lc import live_pauses

# Decision vocabulary accepted by HumanInTheLoopMiddleware. "respond" is the one
# that answers *instead of* running the tool — the AskUserQuestion analogue.
APPROVE = "approve"
REJECT = "reject"


class ToolCallingFake(FakeMessagesListChatModel):
    """Fake model that accepts `bind_tools`, so it can drive an agent loop.

    The stock fakes raise NotImplementedError on bind_tools, which the agent
    factory always calls.
    """

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 - fake ignores the schema
        return self


@pytest.fixture
def crawled():
    """Accumulator proving whether the guarded tool actually executed."""
    return []


@pytest.fixture
def crawl_tool(crawled):
    @tool
    def crawl_page(url: str) -> str:
        """Crawl a page and return its title."""
        crawled.append(url)
        return f"title of {url}"

    return crawl_page


def _agent(crawl_tool, url: str, final: str = "done"):
    """Agent whose model calls the guarded tool once, then answers."""
    model = ToolCallingFake(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "crawl_page", "args": {"url": url}, "id": "call_1"}],
            ),
            AIMessage(content=final),
        ]
    )
    agent = create_deep_agent(
        model=model,
        tools=[crawl_tool],
        system_prompt="You audit sites.",
        interrupt_on={"crawl_page": True},
        # Interrupts need durable state to resume from — no checkpointer, no HITL.
        checkpointer=InMemorySaver(),
    )
    return agent, {"configurable": {"thread_id": str(uuid.uuid4())}}


def test_tool_pauses_before_running(crawl_tool, crawled):
    """The safety property: nothing executes until a human approves."""
    agent, cfg = _agent(crawl_tool, "https://getduct.ai")

    result = agent.invoke({"messages": [{"role": "user", "content": "audit"}]}, cfg)

    assert result.get("__interrupt__"), "expected the graph to pause"
    assert crawled == [], "tool ran before approval"


def test_interrupt_payload_is_serialisable(crawl_tool):
    """The payload has to survive a trip through SSE to the browser."""
    agent, cfg = _agent(crawl_tool, "https://getduct.ai")

    result = agent.invoke({"messages": [{"role": "user", "content": "audit"}]}, cfg)
    payload = result["__interrupt__"][0].value

    encoded = json.dumps(payload)  # raises if anything in there is not JSON-safe
    assert "action_requests" in payload
    request = payload["action_requests"][0]
    assert request["name"] == "crawl_page"
    assert request["args"] == {"url": "https://getduct.ai"}
    assert "crawl_page" in encoded


def test_approval_resumes_and_runs_the_tool(crawl_tool, crawled):
    agent, cfg = _agent(crawl_tool, "https://getduct.ai", final="Audit complete")
    agent.invoke({"messages": [{"role": "user", "content": "audit"}]}, cfg)

    agent.invoke(Command(resume={"decisions": [{"type": APPROVE}]}), cfg)

    assert crawled == ["https://getduct.ai"]
    state = agent.get_state(cfg)
    assert state.values["messages"][-1].content == "Audit complete"
    assert not state.next, "graph should be complete after resuming"


def test_rejection_blocks_the_tool(crawl_tool, crawled):
    agent, cfg = _agent(crawl_tool, "https://blocked.example", final="Skipping")
    agent.invoke({"messages": [{"role": "user", "content": "audit"}]}, cfg)

    agent.invoke(
        Command(resume={"decisions": [{"type": REJECT, "message": "not allowed"}]}), cfg
    )

    assert crawled == [], "tool ran despite rejection"


def test_streaming_emits_token_and_state_events(crawl_tool):
    """`messages` carries token deltas, `updates` carries node state — together
    they replace core/stream.py's pump."""
    agent, cfg = _agent(crawl_tool, "https://getduct.ai")
    agent.invoke({"messages": [{"role": "user", "content": "audit"}]}, cfg)

    modes = {
        mode
        for mode, _chunk in agent.stream(
            Command(resume={"decisions": [{"type": APPROVE}]}),
            cfg,
            stream_mode=["updates", "messages"],
        )
    }

    assert {"messages", "updates"} <= modes


def test_unguarded_tools_do_not_interrupt(crawled):
    """Only tools named in interrupt_on pause — everything else runs freely."""

    @tool
    def safe_lookup(term: str) -> str:
        """Look something up."""
        crawled.append(term)
        return "ok"

    model = ToolCallingFake(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "safe_lookup", "args": {"term": "seo"}, "id": "c1"}],
            ),
            AIMessage(content="done"),
        ]
    )
    agent = create_deep_agent(
        model=model,
        tools=[safe_lookup],
        interrupt_on={"crawl_page": True},  # a different tool
        checkpointer=InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}

    result = agent.invoke({"messages": [{"role": "user", "content": "look up seo"}]}, cfg)

    assert not result.get("__interrupt__")
    assert crawled == ["seo"]


# ---------------------------------------------------------------------------
# interrupt() raised from inside a tool — what agents/core/lc.interrupt_pause
# and the insights runner's resume path stand on. If any of these move, the
# pause port's LangGraph half has to be re-read, not just re-asserted.
# ---------------------------------------------------------------------------

def _two_pauses():
    """An agent whose model asks two tools to pause in the same turn."""

    @tool
    async def ask_goal(q: str) -> str:
        """Ask the user their goal."""
        return f"goal={interrupt({'event': 'questions_required', 'q': q})}"

    @tool
    async def pick_account(q: str) -> str:
        """Ask the user which account."""
        return f"account={interrupt({'event': 'account_selection_required', 'q': q})}"

    model = ToolCallingFake(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "ask_goal", "args": {"q": "goal?"}, "id": "c1"},
                    {"name": "pick_account", "args": {"q": "ga4"}, "id": "c2"},
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    agent = create_deep_agent(
        model=model, tools=[ask_goal, pick_account], system_prompt="x",
        checkpointer=InMemorySaver(),
    )
    return agent, {"configurable": {"thread_id": str(uuid.uuid4())}}


async def _pauses_in(agent, inp, cfg):
    found = []
    async for mode, chunk in agent.astream(inp, cfg, stream_mode=["messages", "updates"]):
        if mode == "updates" and isinstance(chunk, dict):
            found += [(i.id, i.value["event"]) for i in chunk.get("__interrupt__") or ()]
    return found


async def test_a_tool_interrupt_surfaces_in_the_stream_with_an_id():
    """Both pauses arrive in one `updates` chunk, each with the id a resume
    needs — the payload is ours verbatim, so the SSE event is the value."""
    agent, cfg = _two_pauses()

    found = await _pauses_in(agent, {"messages": [{"role": "user", "content": "go"}]}, cfg)

    assert [e for _, e in found] == ["questions_required", "account_selection_required"]
    assert all(i for i, _ in found)


async def test_resuming_one_pause_by_id_re_raises_the_other():
    """Answers arrive one card at a time. Resuming by id must settle that one
    and bring the other back, rather than dropping it or answering both."""
    agent, cfg = _two_pauses()
    first = await _pauses_in(agent, {"messages": [{"role": "user", "content": "go"}]}, cfg)
    goal_id, account_id = first[0][0], first[1][0]

    again = await _pauses_in(agent, Command(resume={goal_id: {"goal": "demo"}}), cfg)
    assert again == [(account_id, "account_selection_required")]

    last = await _pauses_in(agent, Command(resume={account_id: {"account_id": "1"}}), cfg)
    assert last == []
    state = await agent.aget_state(cfg)
    assert not state.next
    assert state.values["messages"][-1].content == "done"


async def test_streaming_none_re_raises_the_live_pauses():
    """The resume path streams None: an unfinished run continues, a parked one
    shows its pauses again, an idle one does nothing. `live_pauses` is what
    tells a pause that is still waiting from one whose task already finished —
    `snapshot.interrupts` keeps both."""
    agent, cfg = _two_pauses()
    first = await _pauses_in(agent, {"messages": [{"role": "user", "content": "go"}]}, cfg)

    assert await _pauses_in(agent, None, cfg) == first

    goal_id = first[0][0]
    await _pauses_in(agent, Command(resume={goal_id: {"goal": "demo"}}), cfg)
    state = await agent.aget_state(cfg)
    assert len(state.interrupts) == 2, "the snapshot keeps the settled one"
    assert [p["event"] for p in live_pauses(state)] == ["account_selection_required"]

    await _pauses_in(agent, Command(resume={first[1][0]: {"account_id": "1"}}), cfg)
    assert await _pauses_in(agent, None, cfg) == []  # idle: nothing to re-raise
