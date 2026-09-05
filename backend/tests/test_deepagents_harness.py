"""What ``interrupt()`` raised from inside a tool does on this ``deepagents`` pin.

``agents/core/lc.interrupt_pause`` and the insights runner's resume path stand
on three behaviours of the harness. ``deepagents`` is 0.x with no stability
policy, so they are pinned here rather than assumed — if one moves on a
dependency bump, the pause port's LangGraph half has to be re-read, not just
re-asserted:

  * two tools pausing in one turn arrive in one ``updates`` chunk, each with
    the id a resume needs, and the payload is ours verbatim;
  * resuming one pause by id settles that one and re-raises the other;
  * streaming ``None`` re-raises the live pauses, and ``live_pauses`` tells a
    pause still waiting from one whose task already finished.

The ``interrupt_on`` (human-in-the-loop middleware) tests that used to sit
above these are gone: no runner mounts ``interrupt_on``, and a gate on a
feature nothing uses is a dependency bump failing a release for nothing. Bring
them back with the first consumer.

A fake chat model drives these so the harness is under test, not a provider —
they must stay green with no API key and no network.
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from deepagents import create_deep_agent
from agents.core.lc import live_pauses
from tests.fakes import ToolCallingFake


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
        # Interrupts need durable state to resume from — no checkpointer, no pause.
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
