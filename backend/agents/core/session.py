"""Shared in-process session registry + AskUserQuestion bridge for streaming agents.

One registry and one human-in-the-loop bridge for every Claude-SDK agent, so
audit / content / future agents stop copy-pasting the identical plumbing. Each
agent's session model subclasses ``BaseAgentSession`` to add its own fields.

In-process only (not shared across Railway instances) — same as before.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from agents.core.events import AgentEvent

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict], Awaitable[None]]

# Default wait for an AskUserQuestion answer before giving up.
ASK_USER_TIMEOUT = 120.0


@dataclass(kw_only=True)
class BaseAgentSession:
    """Fields every streaming-agent session needs. Subclass to add agent extras.

    ``kw_only`` so subclasses can declare required fields after these defaulted
    ones without dataclass ordering errors.
    """

    session_id: str
    agent_type: str = ""
    event_queue: Any                  # asyncio.Queue — agent → SSE consumer
    chat_queue: Any                   # asyncio.Queue — user messages → agent
    answer_future: Any | None = None  # asyncio.Future | None — AskUserQuestion bridge
    created_at: float = 0.0           # time.monotonic() at registration
    last_activity: float = 0.0        # time.monotonic() of last consumer/user activity — drives stale pruning
    pipeline_task: Any | None = None  # asyncio.Task — cancelled on close
    grace_task: Any | None = None     # asyncio.Task — closes the session if no consumer reconnects in time


# Single shared registry across all agent types (UUID keys — no collisions).
_sessions: dict[str, BaseAgentSession] = {}


def get_session(session_id: str) -> BaseAgentSession | None:
    return _sessions.get(session_id)


def register_session(session: BaseAgentSession) -> BaseAgentSession:
    """Register a freshly-built session, stamping created_at if unset."""
    if not session.created_at:
        session.created_at = time.monotonic()
    if not session.last_activity:
        session.last_activity = session.created_at
    _sessions[session.session_id] = session
    return session


def touch_session(session: BaseAgentSession | None) -> None:
    """Mark a session as active *now*. Called whenever a live SSE consumer reads
    a frame (data or keep-alive ping) or the user sends a message, so the stale
    pruner measures inactivity rather than total age — an actively-streaming
    session is never killed just for being long-lived. No-op on None."""
    if session is not None:
        session.last_activity = time.monotonic()


def close_session(session_id: str) -> None:
    """Pop a session, cancel its background pipeline task, and signal its chat
    generator to stop. Safe to call multiple times / on unknown ids."""
    session = _sessions.pop(session_id, None)
    if session is None:
        return
    task = session.pipeline_task
    if task is not None and not task.done():
        task.cancel()
    grace = session.grace_task
    if grace is not None and not grace.done():
        grace.cancel()
    try:
        session.chat_queue.put_nowait(None)  # sentinel — stops the chat-queue loop
    except Exception:
        pass
    try:
        session.event_queue.put_nowait(None)  # sentinel — ends the SSE stream (_sse_stream)
    except Exception:
        pass


def close_all_sessions() -> None:
    """Close every registered session. Called on server shutdown so long-lived
    SSE streams drain immediately — otherwise uvicorn's graceful shutdown blocks
    waiting for them (a --reload or a deploy hangs until the chat idle-timeout).
    Iterates a snapshot since close_session mutates the registry."""
    for session_id in list(_sessions.keys()):
        close_session(session_id)


async def bridge_user_input(
    session: BaseAgentSession,
    session_id: str,
    *,
    event: str,
    payload: dict,
    emit: EmitFn,
    timeout: float = ASK_USER_TIMEOUT,
    log_prefix: str = "agent",
) -> dict:
    """Park a run until a human responds, then resume it.

    The one suspension primitive. Emit ``event`` carrying ``payload``, await an
    ``asyncio.Future`` the messages route resolves, and return whatever the user
    sent back ({} on timeout, which every caller must treat as "carry on
    without it" rather than as an error).

    Three kinds ride this today — a clarifying question, a request to connect a
    data source, and an account choice — and they differ only in the event name
    and what the UI renders. Keeping one Future means the messages route, the
    reconnect grace and the stale pruner all stay unaware of how many kinds
    exist.

    LangGraph's ``interrupt()`` is the upgrade path when a parked run must
    survive a process restart; it plugs in here without the route or the
    frontend noticing (see ``agents/core/ports``).
    """
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    session.answer_future = fut
    await emit({"event": event, "session_id": session_id, **payload})
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("%s: %s timed out for session %s", log_prefix, event, session_id)
        return {}
    finally:
        session.answer_future = None


async def bridge_ask_user_question(
    session: BaseAgentSession,
    session_id: str,
    input_data: dict,
    emit: EmitFn,
    *,
    timeout: float = ASK_USER_TIMEOUT,
    log_prefix: str = "agent",
) -> dict:
    """AskUserQuestion over :func:`bridge_user_input`, in the SDK's tool-input
    shape: returns ``{"questions": [...], "answers": {...}}`` with empty answers
    on timeout, which is what the v3 ``can_use_tool`` hook expects back.
    """
    questions = input_data.get("questions", [])
    answers = await bridge_user_input(
        session,
        session_id,
        event=AgentEvent.QUESTIONS_REQUIRED,
        payload={"questions": questions},
        emit=emit,
        timeout=timeout,
        log_prefix=log_prefix,
    )
    return {"questions": questions, "answers": answers}
