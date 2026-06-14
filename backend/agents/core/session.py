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


async def bridge_ask_user_question(
    session: BaseAgentSession,
    session_id: str,
    input_data: dict,
    emit: EmitFn,
    *,
    timeout: float = ASK_USER_TIMEOUT,
    log_prefix: str = "agent",
) -> dict:
    """Pause on AskUserQuestion: emit QUESTIONS_REQUIRED, await the user's answer
    via an asyncio.Future (resolved by the messages route), and return the
    updated tool input. Empty answers on timeout. This is the bridge that audit
    and content previously duplicated verbatim.
    """
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    session.answer_future = fut
    await emit({
        "event": AgentEvent.QUESTIONS_REQUIRED,
        "session_id": session_id,
        "questions": input_data.get("questions", []),
    })
    try:
        answers = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("%s: AskUserQuestion timed out for session %s", log_prefix, session_id)
        answers = {}
    finally:
        session.answer_future = None
    return {"questions": input_data.get("questions", []), "answers": answers}
