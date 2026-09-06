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
    MODEL_RETRY_HEADER_MAX_DELAY,
    UsageTracker,
    _dispatch_updates,
    is_middleware_node,
    is_summarization_node,
    retry_delay,
    usage_from_messages,
)
from agents.models import CONTEXT_WINDOW, DEFAULT_CONTEXT_WINDOW, PRICING, ModelName, cost_usd


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
        # 300 uncached in at $2 + 900 cached at $0.20 + 40 out at $10, per million.
        "cost_usd": round((300 * 2.0 + 900 * 0.2 + 40 * 10.0) / 1_000_000, 6),
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
    assert billed["cost_usd"] is None  # unpriced: tokens shown, no dollar figure


def test_the_summarisers_call_is_billed_but_does_not_drive_the_gauge():
    tracker = UsageTracker(ModelName.CLAUDE_SONNET)
    billed = tracker.feed(
        AIMessageChunk(content="", usage_metadata=_usage(150_000, 900), response_metadata={"stop_reason": "end_turn"}),
        {"langgraph_node": "_DeepAgentsSummarizationMiddleware.before_model"},
    )
    assert billed["scope"] == "compaction"
    assert billed["input_tokens"] == 150_000  # still on the bill


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
    usage = usage_from_messages(messages, ModelName.CLAUDE_OPUS)
    first = cost_usd(ModelName.CLAUDE_OPUS, input_tokens=100, output_tokens=10)
    second = cost_usd(ModelName.CLAUDE_OPUS, input_tokens=300, output_tokens=20, cache_read_tokens=50)
    assert usage["last"] == {"input_tokens": 300, "output_tokens": 20, "cache_read_tokens": 50, "cost_usd": second}
    assert usage["total"] == {
        "input_tokens": 400, "output_tokens": 30, "cache_read_tokens": 50, "calls": 2,
        "cost_usd": round(first + second, 6),
    }
    assert usage["context_window"] == CONTEXT_WINDOW[ModelName.CLAUDE_OPUS]
    assert usage["model"] == "claude-opus-5"
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


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def test_every_model_with_a_context_window_has_a_price():
    """The two tables describe the same chat models; a model added to one and
    not the other shows a gauge with no cost, or a cost with no gauge."""
    assert set(PRICING) == set(CONTEXT_WINDOW)


def test_cached_tokens_are_priced_at_the_cache_rate_not_the_input_rate():
    # 10 000 in, of which 8 000 were read from cache: only 2 000 at full price.
    full = cost_usd(ModelName.CLAUDE_SONNET, input_tokens=10_000, output_tokens=0)
    mostly_cached = cost_usd(ModelName.CLAUDE_SONNET, input_tokens=10_000, output_tokens=0, cache_read_tokens=8_000)
    assert full == 0.02
    assert mostly_cached == round((2_000 * 2.0 + 8_000 * 0.2) / 1_000_000, 6)
    assert cost_usd("a-model-nobody-priced", input_tokens=1, output_tokens=1) is None


# ---------------------------------------------------------------------------
# Retry delay
# ---------------------------------------------------------------------------

class _Told(Exception):
    def __init__(self, seconds):
        super().__init__("429")
        self.response = type("R", (), {"headers": {"retry-after": str(seconds)}})()


def test_the_providers_retry_after_wins_over_the_schedule_up_to_a_cap():
    assert retry_delay(1, _Told(7)) == 7.0
    assert retry_delay(3, _Told(0)) == 0.0
    assert retry_delay(1, _Told(600)) == MODEL_RETRY_HEADER_MAX_DELAY
    # Nothing said: the jittered schedule, which grows with the attempt.
    assert 0.7 <= retry_delay(1, Exception("429")) <= 1.3
    assert 5.9 <= retry_delay(4) <= 10.1
