"""Fake chat models that drive the real V1 agent loop — no API key, no network.

Four test modules each carried their own copy of ``ToolCallingFake``, and two
of them the failing variants beside it. One copy here, so a change to how the
loop is faked (a new failure shape, a provider's new stop marker) lands once.

The property that matters, and the one the stock LangChain fakes lack: they
raise ``NotImplementedError`` on ``bind_tools``, which every agent factory
calls. These accept it and ignore the schema, so a canned response can carry
``tool_calls`` and the harness runs the real tool.

``FakeMessagesListChatModel`` *cycles* its responses rather than exhausting
them: a two-turn test needs two entries, and a turn that must fail needs
``RaisingFake`` or ``FlakyFake`` rather than an empty list.
"""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


class ToolCallingFake(FakeMessagesListChatModel):
    """A fake that accepts ``bind_tools``, so it can drive a real agent loop."""

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 - the fake ignores the schema
        return self


class RaisingFake(ToolCallingFake):
    """Answers the first call, then fails — the "one bad turn" case."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if getattr(self, "_used", False):
            raise RuntimeError("provider blew up")
        self._used = True
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class RateLimitError(Exception):
    """Named like the provider SDK's, which is how the classifier knows it."""


class AuthenticationError(Exception):
    """Ditto — a rejected key, which must not be retried."""


class FlakyFake(ToolCallingFake):
    """Fails ``failures`` times with ``exc``, then answers — a provider having a moment."""

    failures: int = 2
    exc: type[Exception] = RateLimitError

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        calls = getattr(self, "_calls", 0)
        self._calls = calls + 1
        if calls < self.failures:
            raise self.exc("429 rate limited")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def fake_llm(*responses: str, cls: type[ToolCallingFake] = ToolCallingFake) -> ToolCallingFake:
    """A fake that replies with ``responses`` in order, one per model call."""
    return cls(responses=[AIMessage(content=r) for r in responses])


def tool_names(agent) -> set[str]:
    """Tool names bound into a compiled agent graph.

    Walks the graph rather than asking the runner, so a tool the runner
    *believes* it mounted but the harness dropped shows up as absent.
    """
    for node in agent.nodes.values():
        seq = getattr(getattr(node, "bound", None), "steps", None) or []
        for step in seq:
            if hasattr(step, "tools_by_name"):
                return set(step.tools_by_name)
    # Fall back to the ToolNode's registry wherever it lives.
    tool_node = agent.nodes.get("tools")
    inner = getattr(tool_node, "bound", tool_node)
    return set(getattr(inner, "tools_by_name", {}))


class ContextOverflowError(Exception):
    """The provider's "prompt is too long" — LangChain's name for it, which is
    how the classifier knows it."""


class OverflowFake(ToolCallingFake):
    """Rejects the request as too long `overflows` times, the way a provider
    does when the summariser's estimate ran behind the real count; answers
    otherwise — including the summary an emergency compaction asks it for.
    Set `_overflowed = -1` to let one turn through before the overflows start."""

    overflows: int = 1

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # The summary request carries the summariser's own prompt; it has to
        # succeed or no compaction can happen.
        is_summary = any("extract" in str(getattr(m, "content", "")).lower() for m in messages)
        if not is_summary and getattr(self, "_overflowed", 0) < self.overflows:
            self._overflowed = getattr(self, "_overflowed", 0) + 1
            if self._overflowed > 0:
                raise ContextOverflowError("prompt is too long: 213000 tokens > 200000 maximum")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
