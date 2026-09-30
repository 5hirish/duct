"""What every model call is sent: a stable prefix and an append-only history.

Tier 0 of docs/engineering/2026-09-27-agent-eval-gating-design.md, the free
half of the eval gate. Anthropic's April 2026 Claude Code quality drop was a
harness bug, not a model one: older reasoning was cleared from the history
every turn, so the model lost its own thinking and the cache lost its prefix.
Nothing structural caught it, because the output still looked fine.

Here a recording fake sits where the provider would, over several turns of
the real assembly, and three things must hold for every call after the first:

* the system prompt is byte-identical (the cached prefix starts there);
* the tool schemas are identical (they sit inside that prefix);
* the previous call's messages are a prefix of this call's, unchanged, so
  nothing earlier in the thread is rewritten, reordered or dropped.

A legitimate break (compaction, pruning past its token trigger) needs far
more context than these scripts carry, so any break here is a regression. If
a middleware is meant to rewrite history, it earns a test of its own saying
exactly when, not an exemption here.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import StructuredTool

from agents.core.checkpoint import get_checkpointer
from agents.core.deep_session import RunLimits, build_deep_session_agent, build_session_agent
from agents.insights.schema import create_insights_session
from agents.insights.v1.runner import AutonomousInsightsRunner
from tests.fakes import RecordingFake

LIMITS = RunLimits(
    model_calls_per_run=20, model_calls_per_thread=100, tool_calls_per_run=20,
    tool_calls_per_thread=100, tool_result_prune_trigger=100_000, tool_results_kept=12,
)


def _lookup(topic: str) -> str:
    """Look something up."""
    return json.dumps({"topic": topic, "value": 42})


LOOKUP = StructuredTool.from_function(func=_lookup, name="Lookup", description="Look something up.")


def _turn(n: int) -> list[AIMessage]:
    """One turn: a tool call, then an answer."""
    return [
        AIMessage(content="", tool_calls=[{"name": "Lookup", "args": {"topic": f"t{n}"}, "id": f"c{n}"}]),
        AIMessage(content=f"Answer {n}."),
    ]


def _key(message: BaseMessage) -> tuple:
    """A message as the provider sees it: role, content, calls, and what a
    tool result answers. Ids are LangGraph's bookkeeping, not the request."""
    return (
        message.type,
        json.dumps(message.content, sort_keys=True, default=str),
        json.dumps([(c["name"], c["args"], c["id"]) for c in getattr(message, "tool_calls", []) or []]),
        getattr(message, "tool_call_id", ""),
    )


def assert_append_only(requests: list[dict]) -> None:
    assert len(requests) >= 4, "the script should have made several calls"
    systems = {_key(r["messages"][0]) for r in requests}
    assert len(systems) == 1, "the system prompt changed between calls: the cached prefix is gone"
    schemas = {json.dumps(r["tools"], sort_keys=True) for r in requests}
    assert len(schemas) == 1, "the tool schemas changed between calls"
    for i, (before, after) in enumerate(zip(requests, requests[1:]), start=2):
        prev = [_key(m) for m in before["messages"]]
        nxt = [_key(m) for m in after["messages"]]
        assert nxt[: len(prev)] == prev, f"call {i} rewrote the history call {i - 1} was sent"


async def _three_turns(agent) -> None:
    # Not id(agent): the checkpointer is process-wide, and CPython reuses a
    # freed object's id, so the second rung could inherit the first rung's
    # thread and send its history. It did, depending on what ran before.
    config = {"configurable": {"thread_id": f"invariants-{uuid4()}"}}
    for n in range(3):
        await agent.ainvoke({"messages": [HumanMessage(content=f"Question {n}")]}, config=config)


@pytest.mark.parametrize("build", [build_session_agent, build_deep_session_agent], ids=["create_agent", "deepagents"])
async def test_both_rungs_send_a_stable_prefix_and_an_append_only_history(build):
    llm = RecordingFake(responses=[m for n in range(3) for m in _turn(n)])
    extra = {"planning": False} if build is build_deep_session_agent else {}
    agent = build(llm=llm, tools=[LOOKUP], system_prompt="You are a test agent.", limits=LIMITS,
                  checkpointer=get_checkpointer(), **extra)
    await _three_turns(agent)
    assert_append_only(llm.requests)


async def test_the_insights_session_keeps_its_prefix_across_follow_ups(emitted):
    """The real runner: its prompt, its tools, its middleware, three turns."""
    session = create_insights_session("invariants")
    for follow_up in ("and on mobile?", "and last month?"):
        await session.chat_queue.put(follow_up)
    await session.chat_queue.put(None)
    calls = [
        AIMessage(content="", tool_calls=[{"name": "ReadConnectorNotes", "args": {"connector_id": "ga4"},
                                           "id": f"n{n}"}]) if n % 2 == 0 else AIMessage(content=f"Read {n}.")
        for n in range(6)
    ]
    llm = RecordingFake(responses=calls)

    await AutonomousInsightsRunner(api_key="unused").run_session(
        session.session_id, emitted, llm=llm, session=session, prompt="How is the site doing?",
        chat_idle_timeout=2.0,
    )

    assert_append_only(llm.requests)


def test_the_check_catches_a_harness_that_clears_what_the_model_said():
    """The April bug, reduced: turn two is sent without turn one's reasoning."""
    system = HumanMessage(content="system")  # stands in; only equality matters here
    turn_one = [system, HumanMessage(content="q1")]
    answered = [*turn_one, AIMessage(content="thinking… answer 1")]
    cleared = [*turn_one, AIMessage(content="answer 1"), HumanMessage(content="q2")]
    requests = [
        {"messages": turn_one, "tools": []},
        {"messages": answered, "tools": []},
        {"messages": [*answered, HumanMessage(content="q2")], "tools": []},
        {"messages": cleared, "tools": []},
    ]
    with pytest.raises(AssertionError, match="call 4 rewrote"):
        assert_append_only(requests)
