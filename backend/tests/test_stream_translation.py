"""The stream translator's units: token usage, compaction, middleware nodes.

`stream_agent` reads two LangGraph streams and turns them into Duct events.
These pin the parts that were wrong in ways nobody saw: a summariser's prose
arriving as the agent's reply, and every old tool call replaying as a fresh
step after each compaction.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk, RemoveMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from agents.core.events import AgentEvent
from agents.core.lc import (
    UsageTracker,
    _dispatch_updates,
    is_middleware_node,
    is_summarization_node,
    usage_from_messages,
)
from agents.models import DEFAULT_CONTEXT_WINDOW, ModelName


def _usage(inp, out, cached=0):
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "input_token_details": {"cache_read": cached},
    }


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

def test_a_call_is_billed_once_at_its_stop_marker():
    tracker = UsageTracker(ModelName.CLAUDE_SONNET)
    # Anthropic: model name on the first chunk, usage on the last.
    first = AIMessageChunk(content="", response_metadata={"model_name": "claude-sonnet-5"})
    assert tracker.feed(first, {}) is None
    middle = AIMessageChunk(content="Hel")
    assert tracker.feed(middle, {}) is None
    last = AIMessageChunk(
        content="", usage_metadata=_usage(1200, 40, cached=900),
        response_metadata={"stop_reason": "end_turn"},
    )
    billed = tracker.feed(last, {})
    assert billed == {
        "event": AgentEvent.TOKEN_USAGE,
        "input_tokens": 1200,
        "output_tokens": 40,
        "cache_read_tokens": 900,
        "cache_creation_tokens": 0,
        "model": "claude-sonnet-5",
        "scope": "thread",
        "total_tokens": 1240,
        "context_window": 200_000,
    }
    assert tracker.flush() is None  # nothing left over


def test_chunk_usage_is_additive_across_a_call():
    tracker = UsageTracker("gpt-5-mini")
    tracker.feed(AIMessageChunk(content="", usage_metadata=_usage(500, 0)), {})
    billed = tracker.feed(
        AIMessageChunk(content="", usage_metadata=_usage(0, 30), response_metadata={"finish_reason": "stop"}),
        {},
    )
    assert (billed["input_tokens"], billed["output_tokens"]) == (500, 30)
    assert billed["context_window"] == 400_000  # from the table, by string id


def test_a_call_without_a_stop_marker_is_billed_at_the_end_of_the_turn():
    tracker = UsageTracker("some-model-we-do-not-know")
    assert tracker.feed(AIMessage(content="whole reply", usage_metadata=_usage(10, 5)), {}) is None
    billed = tracker.flush()
    assert billed["total_tokens"] == 15
    assert billed["context_window"] == DEFAULT_CONTEXT_WINDOW


def test_a_nested_call_is_a_subagents_not_the_threads():
    tracker = UsageTracker(ModelName.CLAUDE_SONNET)
    billed = tracker.feed(
        AIMessageChunk(content="", usage_metadata=_usage(1, 1), response_metadata={"stop_reason": "end_turn"}),
        {"langgraph_checkpoint_ns": "tools:abc|model:def"},
    )
    assert billed["scope"] == "subagent"


def test_stored_usage_is_the_last_call_and_the_sum_of_what_survives():
    messages = [
        AIMessage(content="a", usage_metadata=_usage(100, 10)),
        ToolMessage(content="x", tool_call_id="1"),
        AIMessage(content="b", usage_metadata=_usage(300, 20, cached=50)),
    ]
    usage = usage_from_messages(messages, ModelName.CLAUDE_OPUS_1M)
    assert usage["last"] == {"input_tokens": 300, "output_tokens": 20, "cache_read_tokens": 50}
    assert usage["total"] == {"input_tokens": 400, "output_tokens": 30, "cache_read_tokens": 50, "calls": 2}
    assert usage["context_window"] == 1_000_000
    assert usage["model"] == "claude-opus-5[1m]"
    assert usage_from_messages([], ModelName.CLAUDE_SONNET)["last"] is None


# ---------------------------------------------------------------------------
# Middleware nodes
# ---------------------------------------------------------------------------

def test_middleware_nodes_are_recognised_by_their_hook_suffix():
    assert is_middleware_node("_DeepAgentsSummarizationMiddleware.before_model")
    assert is_middleware_node("ContextEditingMiddleware.before_model")
    assert not is_middleware_node("model")
    assert not is_middleware_node("tools")
    assert is_summarization_node("_DeepAgentsSummarizationMiddleware.before_model")
    assert not is_summarization_node("ContextEditingMiddleware.before_model")


async def _collect():
    calls = {"tool_use": [], "compacted": 0}

    async def on_tool_use(name, args, call_id):
        calls["tool_use"].append(name)

    async def on_compacted():
        calls["compacted"] += 1

    return calls, on_tool_use, on_compacted


async def test_a_compaction_is_reported_and_its_surviving_tool_calls_are_not_replayed():
    calls, on_tool_use, on_compacted = await _collect()
    surviving = AIMessage(
        content="", tool_calls=[{"name": "fetch_ga4", "args": {}, "id": "old"}]
    )
    await _dispatch_updates(
        {"_DeepAgentsSummarizationMiddleware.before_model": {
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), surviving],
        }},
        on_todo=None, on_tool_use=on_tool_use, on_tool_result=None, on_compacted=on_compacted,
    )
    assert calls["compacted"] == 1
    assert calls["tool_use"] == []  # the old fetch did not become a new step


async def test_pruning_tool_results_is_not_a_compaction():
    calls, on_tool_use, on_compacted = await _collect()
    await _dispatch_updates(
        {"ContextEditingMiddleware.before_model": {"messages": [AIMessage(content="edited")]}},
        on_todo=None, on_tool_use=on_tool_use, on_tool_result=None, on_compacted=on_compacted,
    )
    assert calls["compacted"] == 0
    assert calls["tool_use"] == []


async def test_the_agent_loops_own_tool_calls_still_dispatch():
    calls, on_tool_use, on_compacted = await _collect()
    await _dispatch_updates(
        {"model": {"messages": [AIMessage(content="", tool_calls=[{"name": "fetch_ga4", "args": {}, "id": "n"}])]}},
        on_todo=None, on_tool_use=on_tool_use, on_tool_result=None, on_compacted=on_compacted,
    )
    assert calls["tool_use"] == ["fetch_ga4"]
    assert calls["compacted"] == 0


# ---------------------------------------------------------------------------
# Steering
# ---------------------------------------------------------------------------

def test_the_steer_middleware_hands_the_model_what_arrived_mid_turn():
    import asyncio

    from agents.core.lc import SteerMiddleware

    class Session:
        steer_queue = asyncio.Queue()

    session = Session()
    session.steer_queue.put_nowait({"role": "user", "content": "also mobile", "client_message_id": "m1"})
    session.steer_queue.put_nowait({"role": "user", "content": [{"type": "text", "text": "and tablets"}]})
    session.steer_queue.put_nowait({"role": "user", "content": ""})  # nothing to say

    update = SteerMiddleware(session).before_model({}, None)
    assert [m.content for m in update["messages"]] == ["also mobile", [{"type": "text", "text": "and tablets"}]]
    assert session.steer_queue.empty()
    # Nothing waiting: no update, so the graph state is untouched.
    assert SteerMiddleware(session).before_model({}, None) is None
    assert SteerMiddleware(object()).before_model({}, None) is None  # a harness with no queue
