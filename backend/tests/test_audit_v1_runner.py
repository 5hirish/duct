"""Audit V1 runner — SSE event contract and the mid-run question bridge.

V1 runs alongside V3, so the frontend must not be able to tell them apart. These
assert the shared `AgentEvent` vocabulary is what reaches the stream, and that
AskUserQuestion still pauses the agent on an asyncio.Future resolved by the
messages route (`agents/core/session.py`) rather than needing new plumbing.

Fake chat model throughout — no API key, no network.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agents.audit.schema import CrawlPlan, CrawlResult
from agents.audit.v1.runner import (
    MAX_QUESTIONS,
    build_audit_agent,
    build_ask_user_tool,
    _split_chunk,
    stream_audit,
)
from agents.core.events import AgentEvent
from agents.core.session import BaseAgentSession, register_session


class ToolCallingFake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self


@pytest.fixture
def crawl_result():
    return CrawlResult(plan=CrawlPlan(root_url="https://getduct.ai"))


@pytest.fixture
def session():
    return register_session(
        BaseAgentSession(
            session_id=str(uuid.uuid4()),
            agent_type="audit_seo",
            event_queue=asyncio.Queue(),
            chat_queue=asyncio.Queue(),
        )
    )


async def _wait_for_event(events: list, timeout: float = 2.0) -> dict:
    """Wait until the tool has emitted, rather than guessing a tick count.

    `tool.ainvoke` goes through LangChain's callback machinery before reaching
    our coroutine, so a single `sleep(0)` is not enough.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while not events:
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("tool never emitted an event")
        await asyncio.sleep(0.01)
    return events[-1]


@pytest.fixture
def emitted():
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    emit.events = events  # type: ignore[attr-defined]
    return emit


# ---------------------------------------------------------------------------
# Mid-run questions
# ---------------------------------------------------------------------------

async def test_ask_user_emits_questions_and_waits_for_the_answer(session, emitted):
    tool = build_ask_user_tool(session, session.session_id, emitted)
    questions = [{"question": "What is the primary conversion goal?", "header": "Goal"}]

    task = asyncio.create_task(tool.ainvoke({"questions": questions}))
    event = await _wait_for_event(emitted.events)

    # The agent is parked until the route resolves the future.
    assert not task.done()
    assert event["event"] == AgentEvent.QUESTIONS_REQUIRED
    assert event["session_id"] == session.session_id
    assert event["questions"] == questions

    session.answer_future.set_result({"Goal": "Demo bookings"})
    result = await task

    assert "Demo bookings" in result


async def test_ask_user_caps_the_number_of_questions(session, emitted):
    tool = build_ask_user_tool(session, session.session_id, emitted)
    many = [{"question": f"q{i}", "header": f"h{i}"} for i in range(10)]

    task = asyncio.create_task(tool.ainvoke({"questions": many}))
    event = await _wait_for_event(emitted.events)

    assert len(event["questions"]) == MAX_QUESTIONS
    session.answer_future.set_result({})
    await task


async def test_ask_user_timeout_tells_the_model_to_continue(session, emitted):
    """An unanswered question must not strand the audit.

    The timeout is injected, not monkeypatched: `bridge_ask_user_question` binds
    ASK_USER_TIMEOUT as a default argument at import time, so patching the module
    attribute has no effect and the test would really wait two minutes.
    """
    tool = build_ask_user_tool(session, session.session_id, emitted, timeout=0.01)

    result = await tool.ainvoke({"questions": [{"question": "q", "header": "h"}]})

    assert "did not answer" in result
    assert "do not ask again" in result


# ---------------------------------------------------------------------------
# Agent assembly
# ---------------------------------------------------------------------------

def test_ask_user_tool_only_present_with_a_session(crawl_result, session, emitted):
    llm = ToolCallingFake(responses=[AIMessage(content="ok")])

    without = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit"
    )
    with_session = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit",
        session=session, session_id=session.session_id, emit=emitted,
    )

    assert "AskUserQuestion" not in _tool_names(without)
    assert "AskUserQuestion" in _tool_names(with_session)


def _tool_names(agent) -> set[str]:
    """Tool names bound into a compiled agent graph."""
    for node in agent.nodes.values():
        seq = getattr(getattr(node, "bound", None), "steps", None) or []
        for step in seq:
            if hasattr(step, "tools_by_name"):
                return set(step.tools_by_name)
    # Fall back to the ToolNode's registry wherever it lives.
    tool_node = agent.nodes.get("tools")
    inner = getattr(tool_node, "bound", tool_node)
    return set(getattr(inner, "tools_by_name", {}))


# ---------------------------------------------------------------------------
# Streaming contract
# ---------------------------------------------------------------------------

async def test_stream_emits_the_shared_event_vocabulary(crawl_result, emitted):
    llm = ToolCallingFake(responses=[AIMessage(content="Audit looks healthy.")])
    agent = build_audit_agent(crawl_result=crawl_result, llm=llm, system_prompt="audit")

    async def on_close(_raw: str, _turn: str) -> None:
        pass

    await stream_audit(agent, "audit getduct.ai", emitted, on_report_close=on_close)

    kinds = [e["event"] for e in emitted.events]
    assert AgentEvent.MESSAGE_STOP in kinds
    assert AgentEvent.AGENT_MESSAGE_CHUNK in kinds
    # Only the shared vocabulary reaches the frontend.
    assert set(kinds) <= set(AgentEvent)


async def test_stream_routes_report_payload_to_the_parser(crawl_result, emitted):
    """Text inside <duct_report> is REPORT_CHUNK, prose outside is a message."""
    llm = ToolCallingFake(
        responses=[AIMessage(content="Summary first.<duct_report>{\"a\":1}</duct_report>")]
    )
    agent = build_audit_agent(crawl_result=crawl_result, llm=llm, system_prompt="audit")

    closed: list[tuple[str, str]] = []

    async def on_close(raw: str, turn: str) -> None:
        closed.append((raw, turn))

    await stream_audit(agent, "audit", emitted, on_report_close=on_close)

    assert closed, "the report tag should have closed"
    raw, _turn = closed[0]
    assert "\"a\":1" in raw
    prose = "".join(
        e["text"] for e in emitted.events if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK
    )
    assert "Summary first." in prose
    assert "duct_report" not in prose, "the tag must not leak into user-facing prose"


# ---------------------------------------------------------------------------
# Provider content shapes
# ---------------------------------------------------------------------------

def test_split_chunk_handles_provider_variations():
    assert _split_chunk(AIMessage(content="plain")) == ("plain", "")
    assert _split_chunk(
        AIMessage(content=[{"type": "text", "text": "visible"}])
    ) == ("visible", "")
    # Anthropic-style reasoning blocks
    assert _split_chunk(
        AIMessage(content=[{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "out"}])
    ) == ("out", "hmm")
    # OpenAI-style reasoning blocks
    assert _split_chunk(
        AIMessage(content=[{"type": "reasoning", "text": "why"}])
    ) == ("", "why")
    # Unknown block types are dropped, never leaked as report text
    assert _split_chunk(AIMessage(content=[{"type": "image", "url": "x"}])) == ("", "")
    assert _split_chunk(None) == ("", "")
