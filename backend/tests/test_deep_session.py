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
    fallback_chain,
    recorder_tool_hooks,
)
from agents.core.events import AgentEvent
from agents.models import ModelName, Provider
from tests.fakes import ToolCallingFake, fake_llm, tool_names


def _limits(**overrides) -> RunLimits:
    base = dict(
        recursion=10, model_calls_per_run=5, model_calls_per_thread=50,
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
