"""What the autonomous insights agent's middleware stack must keep guaranteeing.

Three of these are ordinary presence checks. The fourth is the one worth having:
the relationship between context pruning and summarization is a *threshold*
relationship, not an ordering one, and it is easy to break without noticing.

`deepagents` mounts `SummarizationMiddleware` in its own base stack, and
`_apply_custom_middleware` lands user middleware after the last core entry.
Since `wrap_model_call` composes first-in-list as outermost, summarization
always wraps our `ContextEditingMiddleware` — we cannot put the cheap pass
first by position. What keeps the cheap pass useful is that summarization
delegates straight through below its own trigger (0.85 of the model's window,
or a flat 170k for a model with no profile), so a lower prune trigger sees the
untouched request.

Raise `TOOL_RESULT_PRUNE_TRIGGER` above that floor and nothing fails: pruning
just silently stops happening, and every long run pays for an LLM compaction it
did not need. Hence a test.
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agents.models import ModelName, Provider
from agents.insights.v1.runner import (
    MODEL_CALLS_PER_RUN,
    MODEL_CALLS_PER_THREAD,
    SUMMARIZATION_FLOOR_TOKENS,
    TOOL_CALLS_PER_RUN,
    TOOL_CALLS_PER_THREAD,
    TOOL_RESULT_PRUNE_TRIGGER,
    AutonomousInsightsRunner,
)


@pytest.fixture
def stack(monkeypatch) -> list[str]:
    """Middleware names of a built agent, outermost first."""
    import deepagents.graph as graph

    captured: list[list[str]] = []
    original = graph._apply_custom_middleware

    def _spy(base, custom, **kwargs):
        result = original(base, custom, **kwargs)
        captured.append([m.name for m in result])
        return result

    monkeypatch.setattr(graph, "_apply_custom_middleware", _spy)
    AutonomousInsightsRunner(api_key="unused-no-network").build_agent(
        llm=FakeMessagesListChatModel(responses=[AIMessage(content="ok")]),
    )
    # Subagents are assembled first; the main agent's stack is the longest and
    # is the last one produced.
    return captured[-1]


def test_pruning_must_trigger_below_summarization():
    """The invariant. Above the floor, the cheap pass silently never runs."""
    assert TOOL_RESULT_PRUNE_TRIGGER < SUMMARIZATION_FLOOR_TOKENS


def test_the_summarization_floor_matches_what_deepagents_actually_picks():
    """Pins our copy of deepagents' default to deepagents' own value."""
    from deepagents.middleware.summarization import compute_summarization_defaults

    class _NoProfile(FakeMessagesListChatModel):
        @property
        def profile(self):
            return None

    defaults = compute_summarization_defaults(
        _NoProfile(responses=[AIMessage(content="ok")])
    )
    assert defaults["trigger"] == ("tokens", SUMMARIZATION_FLOOR_TOKENS)


def test_the_spend_guards_are_mounted(stack):
    """No loop guard means a runaway turn bills the customer's own key."""
    assert "ModelCallLimitMiddleware" in stack
    assert "ToolCallLimitMiddleware" in stack


def test_context_editing_is_mounted(stack):
    assert "ContextEditingMiddleware" in stack


def test_summarization_comes_from_deepagents_and_is_not_doubled(stack):
    """We deliberately do not mount our own — the base stack already has one."""
    assert stack.count("SummarizationMiddleware") == 1


def test_summarization_still_wraps_our_pruning(stack):
    """Documents the ordering we cannot change, so the threshold test has a reason.

    If a deepagents release ever lands user middleware *before* the core stack,
    this flips — and the trigger relationship could then be relaxed.
    """
    assert stack.index("SummarizationMiddleware") < stack.index("ContextEditingMiddleware")


def test_the_planning_loop_and_virtual_filesystem_survived(stack):
    """Both are load-bearing: the UI renders todos, and the FS must stay virtual."""
    assert "TodoListMiddleware" in stack
    assert "FilesystemMiddleware" in stack


def test_limits_are_ordered_run_below_thread():
    """A run limit above the thread limit would make the thread limit unreachable."""
    assert MODEL_CALLS_PER_RUN < MODEL_CALLS_PER_THREAD
    assert TOOL_CALLS_PER_RUN < TOOL_CALLS_PER_THREAD


# ---------------------------------------------------------------------------
# Model fallback — mounting only. The registry itself (agents/models.py) and the
# engine policy over it (agents/engines.py) are pinned in test_model_transport.py,
# beside the other model/engine registries.
# ---------------------------------------------------------------------------

def test_the_middleware_mounts_when_a_chain_exists(monkeypatch):
    import deepagents.graph as graph

    captured: list[list[str]] = []
    original = graph._apply_custom_middleware

    def _spy(base, custom, **kwargs):
        result = original(base, custom, **kwargs)
        captured.append([m.name for m in result])
        return result

    monkeypatch.setattr(graph, "_apply_custom_middleware", _spy)
    AutonomousInsightsRunner(
        api_key="unused-no-network",
        provider=Provider.ANTHROPIC,
        model=ModelName.CLAUDE_SONNET,
    ).build_agent()

    assert "ModelFallbackMiddleware" in captured[-1]


def test_an_injected_model_is_never_second_guessed(stack):
    """The `llm=` seam is a deliberate choice; overriding it would fire real
    provider calls out of a fake-model test."""
    assert "ModelFallbackMiddleware" not in stack
