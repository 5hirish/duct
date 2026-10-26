"""Which tool call is executing, for the writers that must survive a replay.

A run cut between a tool's commit and its superstep checkpoint is continued
from the checkpoint, and the checkpoint executes the same tool call again:
the call id in the model's message is the one thing stable across the cut.
A writer keyed on that id turns the second execution into a read of what the
first one wrote; one without it proposes a second change set or mints a
second artifact. ``ToolCallBinder`` in ``agents/core/deep_session.py`` sets
the id around every tool call; a writer reads it here and hands it to its
service. Framework-free on purpose, so the services and the tool bodies stay
importable without LangChain and a test can call a tool body directly.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_EXECUTING: ContextVar[str] = ContextVar("duct_tool_call_id", default="")


def current_tool_call_id() -> str:
    """The id of the tool call this code runs inside, or "" outside one (a
    route, a test calling a tool body directly). Survives ``asyncio.to_thread``,
    which runs the function under a copy of the calling context."""
    return _EXECUTING.get()


@contextmanager
def executing_tool_call(tool_call_id: str) -> Iterator[None]:
    token = _EXECUTING.set(tool_call_id or "")
    try:
        yield
    finally:
        _EXECUTING.reset(token)
