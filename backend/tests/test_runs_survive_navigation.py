"""A run outlives the page that started it; only Stop cancels it.

Closing the page used to delete the session, so opening Connections mid-brief
killed the brief. Now the page detaches and keeps its handle, the run finishes
and is written down, and a tab that comes back hydrates the rows and reattaches
to the live stream from the segment after the ones it already has.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlmodel import Session, select

import agents.content.persistence as persistence
import routes.agents as agents_routes
from agents.content.persistence import SEGMENT_FIELD, ConversationRecorder
from agents.core.events import AgentEvent, EventKind
from agents.core.session import BaseAgentSession, close_session, get_session, register_session
from models.auth import User
from models.content import AgentConversation, AgentEvent as AgentEventRow
from models.project import Project
from tests.conftest import make_sqlite_engine


@pytest.fixture
def engine(monkeypatch):
    engine = make_sqlite_engine()

    def _fake_db():
        yield Session(engine)

    monkeypatch.setattr(persistence, "db_session", _fake_db)
    return engine


@pytest.fixture
def conversation(engine):
    with Session(engine) as db:
        user = User(id=uuid.uuid4(), email="o@example.com")
        project = Project(id=uuid.uuid4(), name="P", user_id=user.id)
        db.add(user)
        db.add(project)
        db.commit()
        conv = AgentConversation(agent_type="insights", project_id=project.id)
        db.add(conv)
        db.commit()
        return conv.id


def _rows(engine, conversation_id) -> list[AgentEventRow]:
    with Session(engine) as db:
        stmt = select(AgentEventRow).where(AgentEventRow.conversation_id == conversation_id).order_by(AgentEventRow.seq)
        return list(db.exec(stmt))


# --- the recorder numbers what it sees and what it writes --------------------

async def test_live_events_and_the_rows_they_leave_share_a_segment(engine, conversation):
    recorder = ConversationRecorder(conversation, session_id="sess-1")
    seen: list[dict] = []

    async def emit(body):
        seen.append(dict(body))

    wrapped = recorder.wrap_emit(emit)
    for event in (
        {"event": AgentEvent.PIPELINE_STARTED},
        {"event": AgentEvent.AGENT_MESSAGE_CHUNK, "text": "first "},
        {"event": AgentEvent.MESSAGE_STOP},
        {"event": AgentEvent.AGENT_MESSAGE_CHUNK, "text": "second"},
        {"event": AgentEvent.MESSAGE_STOP},
        {"event": AgentEvent.PIPELINE_FINISHED},
    ):
        await wrapped(event)

    # The stop that ends a segment carries that segment; what follows is the next.
    assert [b[SEGMENT_FIELD] for b in seen] == [1, 1, 1, 2, 2, 3]
    replies = [r for r in _rows(engine, conversation) if r.kind == EventKind.ASSISTANT]
    assert [(r.data["text"], r.data["session"], r.data[SEGMENT_FIELD]) for r in replies] == [
        ("first", "sess-1", 1),
        ("second", "sess-1", 2),
    ]


async def test_an_event_emitted_elsewhere_keeps_its_own_segment(engine, conversation):
    """A route-side emit may already know its segment; the stamp is a default."""
    recorder = ConversationRecorder(conversation, session_id="sess-1")
    seen: list[dict] = []

    async def emit(body):
        seen.append(dict(body))

    await recorder.wrap_emit(emit)({"event": AgentEvent.PIPELINE_STARTED, SEGMENT_FIELD: 9})
    assert seen[0][SEGMENT_FIELD] == 9


# --- the stream skips what the tab already hydrated --------------------------

async def _frames(queue: asyncio.Queue, **kw) -> list[str]:
    return [f async for f in agents_routes._sse_stream(queue, **kw)]


async def test_reattaching_after_a_segment_skips_its_backlog_and_nothing_else():
    queue: asyncio.Queue = asyncio.Queue()
    for payload in (
        {"event": "a", SEGMENT_FIELD: 1},
        {"event": "b", SEGMENT_FIELD: 1},
        {"event": "c", SEGMENT_FIELD: 2},
        {"event": "d"},  # emitted outside the recorder: never skipped
        {"event": "e", SEGMENT_FIELD: 3},
        None,
    ):
        queue.put_nowait(payload)

    frames = await _frames(queue, skip_through=1)
    assert [f.split('"event": "')[1][0] for f in frames] == ["c", "d", "e"]


async def test_a_fresh_stream_skips_nothing():
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait({"event": "a", SEGMENT_FIELD: 1})
    queue.put_nowait(None)
    assert len(await _frames(queue)) == 1


# --- a detached run finishes; only Stop cancels it ---------------------------

def _session(session_id: str, *, turn_active: bool) -> BaseAgentSession:
    session = BaseAgentSession(
        session_id=session_id, agent_type="insights",
        event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
    )
    session.turn_active = turn_active
    return register_session(session)


async def test_the_grace_close_waits_for_the_turn_the_tab_left_behind(monkeypatch):
    closed: list[str] = []
    monkeypatch.setattr(agents_routes, "_RECONNECT_GRACE", 0.01)
    monkeypatch.setattr(agents_routes, "_close_and_consolidate", closed.append)
    session = _session("detached-run", turn_active=True)
    try:
        agents_routes._schedule_grace_close("detached-run")
        await asyncio.sleep(0.06)
        assert closed == [] and get_session("detached-run") is session

        session.turn_active = False  # the run finished on its own
        await asyncio.sleep(0.04)
        assert closed == ["detached-run"]
    finally:
        close_session("detached-run")


async def test_a_reconnect_still_cancels_the_grace(monkeypatch):
    closed: list[str] = []
    monkeypatch.setattr(agents_routes, "_RECONNECT_GRACE", 0.01)
    monkeypatch.setattr(agents_routes, "_close_and_consolidate", closed.append)
    session = _session("came-back", turn_active=True)
    try:
        agents_routes._schedule_grace_close("came-back")
        agents_routes._cancel_grace(session)
        session.turn_active = False
        await asyncio.sleep(0.04)
        assert closed == []
    finally:
        close_session("came-back")


def test_the_pruner_leaves_a_running_turn_alone(monkeypatch):
    monkeypatch.setattr(agents_routes, "_SESSION_TTL", 10)
    idle = _session("idle-for-ages", turn_active=False)
    busy = _session("busy-for-ages", turn_active=True)
    try:
        idle.last_activity = busy.last_activity = 0.0
        assert agents_routes._stale_session_ids(now=100.0) == ["idle-for-ages"]
    finally:
        close_session("idle-for-ages")
        close_session("busy-for-ages")


async def test_the_session_state_says_whether_a_turn_is_in_flight():
    session = _session("anonymous-run", turn_active=True)
    try:
        state = await agents_routes.get_session_state("insights", "anonymous-run", user=None)
        assert state["running"] is True
        session.turn_active = False
        state = await agents_routes.get_session_state("insights", "anonymous-run", user=None)
        assert state["running"] is False
    finally:
        close_session("anonymous-run")
