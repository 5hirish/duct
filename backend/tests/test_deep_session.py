"""The shared deepagents session (agents/core/deep_session.py).

The two session runners exercise the loop end to end in their own suites
(tests/test_insights_session.py, tests/test_content_v1_runner.py). What is
pinned here is the part that is *only* the shared module's: the guards that
refuse a misconfigured agent at construction, the fallback chain's policy,
the recorder hooks' tolerance of "no recorder", and that both runners really
do assemble through the one factory rather than a private stack.

Fake chat model throughout — no API key, no network.
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import AIMessage

from agents.core.deep_session import (
    SUMMARIZATION_FLOOR_TOKENS,
    DeepSession,
    RunLimits,
    build_deep_session_agent,
    PRUNE_BATCH_DIVISOR,
    build_session_agent,
    fallback_chain,
    session_middleware,
    recorder_tool_hooks,
)
from agents.core.events import AgentEvent
from agents.models import ModelName, Provider
from tests.fakes import ToolCallingFake, fake_llm, tool_names


def _limits(**overrides) -> RunLimits:
    base = dict(
        model_calls_per_run=5, model_calls_per_thread=50,
        tool_calls_per_run=10, tool_calls_per_thread=100,
        tool_result_prune_trigger=1_000, tool_results_kept=2,
    )
    return RunLimits(**{**base, **overrides})


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_a_prune_trigger_above_the_summarization_floor_is_refused():
    """Above the floor the cheap pass silently never runs — so it is an error
    at construction, not a slow surprise in production."""
    with pytest.raises(ValueError, match="summarization floor"):
        _limits(tool_result_prune_trigger=SUMMARIZATION_FLOOR_TOKENS)


def test_a_run_limit_must_sit_below_its_thread_limit():
    with pytest.raises(ValueError):
        _limits(model_calls_per_run=50, model_calls_per_thread=50)
    with pytest.raises(ValueError):
        _limits(tool_calls_per_run=100, tool_calls_per_thread=10)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def test_the_assembled_agent_has_planning_a_virtual_filesystem_and_no_shell():
    agent = build_deep_session_agent(
        llm=fake_llm("ok"), tools=[], system_prompt="x", limits=_limits(),
    )
    names = tool_names(agent)

    assert "write_todos" in names
    assert {"ls", "read_file", "write_file", "edit_file", "glob", "grep"} <= names
    assert "execute" not in names


def test_a_prune_clears_a_batch_so_the_prefix_holds_between_prunes():
    """With no `clear_at_least`, LangChain clears every result older than
    `keep` on every call past the trigger — one more each call, so the cached
    prefix diverged at that result and the provider re-prefilled the tail at
    write price for the rest of the run. A batch drops the count back under
    the trigger and the prefix holds until that much context accumulates."""
    from langchain.agents.middleware import ContextEditingMiddleware

    limits = _limits()
    assert limits.tool_results_clear_at_least == limits.tool_result_prune_trigger // PRUNE_BATCH_DIVISOR
    assert _limits(tool_results_clear_at_least=300).tool_results_clear_at_least == 300
    with pytest.raises(ValueError, match="clear_at_least"):
        _limits(tool_results_clear_at_least=1_000)

    pruning = next(m for m in session_middleware(limits) if isinstance(m, ContextEditingMiddleware))
    (edit,) = pruning.edits
    assert edit.clear_at_least == limits.tool_results_clear_at_least


def test_the_fallback_model_carries_the_threads_cache_key():
    """OpenAI routes a request by `prompt_cache_key`; a fallen-back loop
    without it landed on a machine with no prefix and rebuilt it per call."""
    from langchain_core.messages import HumanMessage

    from agents.core.lc import PROMPT_CACHE_KEY_FIELD

    (fallback,) = fallback_chain(Provider.OPENAI, ModelName.GPT_6_1_SOL, "sk-proj-x", cache_key="thread-1")
    assert fallback._get_request_payload([HumanMessage("hi")])[PROMPT_CACHE_KEY_FIELD] == "thread-1"


def test_fallback_chain_is_one_same_provider_step_or_nothing():
    assert fallback_chain(Provider.ANTHROPIC, ModelName.CLAUDE_HAIKU, "k") == []
    assert fallback_chain(Provider.OPENROUTER, "vendor/unknown-slug", "k") == []
    chain = fallback_chain(Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, "k")
    assert len(chain) == 1


def test_both_session_runners_assemble_through_the_shared_factory(monkeypatch):
    """The point of the extraction: a middleware fix lands once. If either
    runner grows a private stack again, this is where it shows."""
    import agents.core.deep_session as shared
    from agents.content.v1.runner import ContentRunner
    from agents.insights.v1.runner import AutonomousInsightsRunner

    calls: list[str] = []
    original = shared.build_deep_session_agent

    def _spy(**kwargs):
        calls.append(kwargs["system_prompt"][:12])
        return original(**kwargs)

    monkeypatch.setattr("agents.insights.v1.runner.build_deep_session_agent", _spy)
    monkeypatch.setattr("agents.content.v1.runner.build_deep_session_agent", _spy)

    AutonomousInsightsRunner(api_key="unused").build_agent(llm=fake_llm("ok"))
    ContentRunner(api_key="unused").build_agent(llm=fake_llm("ok"), interactive=False)

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

async def test_recorder_hooks_are_inert_without_a_recorder():
    on_use, on_result = recorder_tool_hooks(None)
    await on_use("t", {"a": 1}, "id")
    await on_result("t", "out", "id", False)


async def test_recorder_hooks_write_use_and_result():
    class _Recorder:
        def __init__(self):
            self.rows = []

        async def record_tool_use(self, name, tool_input, tool_use_id):
            self.rows.append(("use", name, tool_use_id))

        async def record_tool_result(self, name, result, tool_use_id, *, is_error):
            self.rows.append(("result", name, tool_use_id, is_error))

    rec = _Recorder()
    on_use, on_result = recorder_tool_hooks(rec)
    await on_use("fetch", {}, "c1")
    await on_result("fetch", "x", "c1", True)
    assert rec.rows == [("use", "fetch", "c1"), ("result", "fetch", "c1", True)]


# ---------------------------------------------------------------------------
# The loop, driven bare — no runner, no session
# ---------------------------------------------------------------------------

async def test_after_turn_can_run_more_turns_and_finish_carries_the_payload(emitted):
    """The two runner-owned hooks: `after_turn` may drive further turns
    (content's nudge) and `finish_payload` decorates the single finish event."""
    llm = ToolCallingFake(responses=[AIMessage(content="first"), AIMessage(content="second")])
    agent = build_deep_session_agent(llm=llm, tools=[], system_prompt="x", limits=_limits())
    turns = {"extra": 0}

    async def _after(pauses):
        if turns["extra"] == 0 and not pauses:
            turns["extra"] += 1
            return await loop.turn("again")
        return pauses

    loop = DeepSession(
        agent, emit=emitted, thread_id=str(uuid.uuid4()), limits=_limits(),
        provider=Provider.ANTHROPIC, model=ModelName.CLAUDE_HAIKU, log_prefix="t",
        summariser=llm, after_turn=_after, finish_payload=lambda: {"mode": "unit"},
    )
    await loop.run("go", resume=False, chat_idle_timeout=0.01)

    kinds = [e["event"] for e in emitted.events]
    assert kinds.count(AgentEvent.MESSAGE_STOP) == 2
    finished = [e for e in emitted.events if e["event"] == AgentEvent.PIPELINE_FINISHED]
    assert len(finished) == 1 and finished[0]["mode"] == "unit"


# ---------------------------------------------------------------------------
# The superstep budget — derived, and enough
# ---------------------------------------------------------------------------

async def test_the_recursion_budget_admits_every_call_the_model_guard_allows():
    """A hand-picked recursion limit of 100 let a plan turn make 14 model calls
    before LangGraph gave up, while the guard meant to end the run sat at 80.
    Now the budget follows the guard: a model that never stops calling tools
    is ended by the model-call limit, never by the graph."""
    from langgraph.errors import GraphRecursionError

    from agents.core.deep_session import RECURSION_SLACK, SUPERSTEPS_PER_MODEL_CALL

    limits = _limits(model_calls_per_run=12, model_calls_per_thread=13)
    assert limits.recursion == 12 * SUPERSTEPS_PER_MODEL_CALL + RECURSION_SLACK

    class _Endless(ToolCallingFake):
        """A fresh tool call every time — the reducer dedupes by message id,
        so a cycled fake would collapse into one row."""
        n: int = 0

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            from langchain_core.outputs import ChatGeneration, ChatResult

            self.n += 1
            message = AIMessage(content="", id=f"ai-{self.n}", tool_calls=[{
                "name": "write_todos", "args": {"todos": [{"content": "again", "status": "pending"}]},
                "id": f"t{self.n}",
            }])
            return ChatResult(generations=[ChatGeneration(message=message)])

    endless = _Endless(responses=[])
    agent = build_deep_session_agent(llm=endless, tools=[], system_prompt="x", limits=limits)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": limits.recursion}
    try:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": "go"}]}, config)
    except GraphRecursionError as exc:
        pytest.fail(f"the graph gave up before the model-call guard did: {exc}")
    calls = sum(1 for m in result["messages"] if getattr(m, "type", "") == "ai" and getattr(m, "tool_calls", None))
    assert calls == 12, "the model-call guard is what ended the turn"


# ---------------------------------------------------------------------------
# Pictures leave the thread once the model has seen them
# ---------------------------------------------------------------------------

async def test_a_tool_result_image_is_replaced_after_the_model_call_that_saw_it():
    """The text block (asset URL, metadata) survives; the base64 does not — a
    durable Postgres thread would otherwise copy every image into every later
    checkpoint of the conversation."""
    from langchain_core.tools import StructuredTool

    from agents.core.lc import SeenImagePruneMiddleware

    async def snap() -> list[dict]:
        return [
            {"type": "image", "base64": "QUFBQQ==", "mime_type": "image/png"},
            {"type": "text", "text": '{"asset_url": "/uploads/x.png"}'},
        ]

    tool = StructuredTool.from_function(coroutine=snap, name="snap", description="take a picture")
    llm = ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "snap", "args": {}, "id": "s1"}]),
        AIMessage(content="looks good"),
    ])
    agent = build_deep_session_agent(
        llm=llm, tools=[tool], system_prompt="x", limits=_limits(), prune_seen_images=True,
    )
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": _limits().recursion}
    await agent.ainvoke({"messages": [{"role": "user", "content": "go"}]}, config)

    snapshot = await agent.aget_state(config)
    tool_messages = [m for m in snapshot.values["messages"] if getattr(m, "type", "") == "tool"]
    assert len(tool_messages) == 1
    kept = tool_messages[0]
    assert kept.tool_call_id == "s1"
    assert "QUFBQQ==" not in str(kept.content)
    texts = [b["text"] for b in kept.content if isinstance(b, dict) and b.get("type") == "text"]
    assert SeenImagePruneMiddleware.PLACEHOLDER in texts and '{"asset_url": "/uploads/x.png"}' in texts


def test_pruning_is_opt_in_and_content_opts_in_only_where_it_sees_pictures():
    from agents.content.v1.runner import ContentRunner

    seen: list[bool] = []
    original = build_deep_session_agent

    def _spy(**kwargs):
        seen.append(kwargs.get("prune_seen_images", False))
        return original(**kwargs)

    import agents.content.v1.runner as runner_module

    runner_module.build_deep_session_agent, restore = _spy, runner_module.build_deep_session_agent
    try:
        ContentRunner(api_key="unused", provider=Provider.ANTHROPIC).build_agent(llm=fake_llm("ok"), interactive=False)
        ContentRunner(api_key="unused", provider=Provider.OPENAI, model=ModelName.GPT_5_MINI).build_agent(
            llm=fake_llm("ok"), interactive=False
        )
    finally:
        runner_module.build_deep_session_agent = restore
    assert seen == [True, False]


# ---------------------------------------------------------------------------
# Fallback only on a failure another model could survive (rulebook gap 4)
# ---------------------------------------------------------------------------

class _Request:
    """The least a fallback loop needs from a ModelRequest."""

    model = None

    def override(self, **_kw):
        return self


@pytest.fixture
def no_sanitize(monkeypatch):
    import langchain.agents.middleware.model_fallback as module

    monkeypatch.setattr(module, "_sanitize_request_for_fallback", lambda request, model: request)


def _failing(status: int):
    exc_type = type("ProviderError", (Exception,), {"status_code": status})
    return exc_type(f"status {status}")


@pytest.mark.parametrize("status", [401, 400, 404])
def test_a_rejected_key_or_bad_request_is_not_retried_on_the_fallback(no_sanitize, status):
    from agents.core.deep_session import ClassifiedFallbackMiddleware

    calls: list[str] = []

    def handler(request):
        calls.append("call")
        raise _failing(status)

    middleware = ClassifiedFallbackMiddleware(fake_llm("fallback"))
    with pytest.raises(Exception, match=f"status {status}"):
        middleware.wrap_model_call(_Request(), handler)
    assert calls == ["call"], "the fallback model must not see a request the primary rejected"


@pytest.mark.parametrize("status", [429, 529, 503])
def test_a_transient_failure_falls_back(no_sanitize, status):
    from agents.core.deep_session import ClassifiedFallbackMiddleware

    calls: list[str] = []

    def handler(request):
        calls.append("call")
        if len(calls) == 1:
            raise _failing(status)
        return "answer"

    middleware = ClassifiedFallbackMiddleware(fake_llm("fallback"))
    assert middleware.wrap_model_call(_Request(), handler) == "answer"
    assert calls == ["call", "call"]


async def test_the_async_path_classifies_the_same_way(no_sanitize):
    from agents.core.deep_session import ClassifiedFallbackMiddleware

    calls: list[int] = []

    async def handler(request):
        calls.append(1)
        raise _failing(401)

    middleware = ClassifiedFallbackMiddleware(fake_llm("fallback"))
    with pytest.raises(Exception, match="status 401"):
        await middleware.awrap_model_call(_Request(), handler)
    assert len(calls) == 1


def test_the_loop_mounts_the_classified_fallback():
    from agents.core.deep_session import ClassifiedFallbackMiddleware, session_middleware

    mounted = [m for m in session_middleware(_limits(), fallbacks=[fake_llm("fallback")])
               if isinstance(m, ClassifiedFallbackMiddleware)]
    assert len(mounted) == 1


# A tool that raises is a result the model reads (rulebook gap 5)
# ---------------------------------------------------------------------------

async def test_a_tool_that_raises_becomes_an_error_the_model_can_read():
    """Duct's tools return their failures as payloads, so a raise is a bug or
    a sub-agent that died — and it used to end the turn after minutes of
    fetching. Now it is an error ToolMessage with the type and a sanitised
    sentence, and the model carries on."""
    from langchain_core.messages import ToolMessage
    from langchain_core.tools import StructuredTool

    def _explode(topic: str) -> str:
        """Look something up."""
        raise RuntimeError("vendor said no at https://vendor.example/v1?key=sk-live-ABCDEFGHIJKLMNOPQRSTUV")

    boom = StructuredTool.from_function(func=_explode, name="Lookup", description="Look something up.")
    llm = ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "Lookup", "args": {"topic": "x"}, "id": "c1"}]),
        AIMessage(content="Could not look it up; here is what I know."),
    ])
    agent = build_session_agent(llm=llm, tools=[boom], system_prompt="x", limits=_limits())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": _limits().recursion}

    result = await agent.ainvoke({"messages": [{"role": "user", "content": "go"}]}, config)

    errors = [m for m in result["messages"] if isinstance(m, ToolMessage) and m.status == "error"]
    assert len(errors) == 1
    text = errors[0].content if isinstance(errors[0].content, str) else str(errors[0].content)
    assert "Lookup failed (RuntimeError)" in text and "carry on" in text
    assert "https://" not in text and "ABCDEFGH" not in text
    assert result["messages"][-1].content == "Could not look it up; here is what I know."
