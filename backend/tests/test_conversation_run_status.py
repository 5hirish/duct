"""Run status is derived from the event stream, once, in the recorder.

A failure used to exist only as an SSE frame: reload the tab and the transcript
ended on the user's message with no reply and no reason, while the desk called
the thread "Open". These pin what the recorder writes for each turn of the
lifecycle, and that a session closed mid-turn is recorded as cancelled.
"""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session, select

import agents.content.persistence as persistence
from agents.content.persistence import ConversationRecorder
from agents.core.events import AgentEvent, EventKind, RunStatus
from models.content import AgentConversation, AgentEvent as AgentEventRow
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
    from models.auth import User
    from models.project import Project

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


def _row(engine, conversation_id) -> AgentConversation:
    with Session(engine) as db:
        return db.get(AgentConversation, conversation_id)


def _kinds(engine, conversation_id) -> list[str]:
    with Session(engine) as db:
        rows = db.exec(select(AgentEventRow).where(AgentEventRow.conversation_id == conversation_id).order_by(AgentEventRow.seq))
        return [r.kind for r in rows]


async def _drive(recorder: ConversationRecorder, *events: dict) -> None:
    async def emit(_body):  # the SSE side; not under test
        return None

    wrapped = recorder.wrap_emit(emit)
    for event in events:
        await wrapped(event)


async def test_a_run_is_running_then_idle(engine, conversation):
    recorder = ConversationRecorder(conversation)
    await _drive(recorder, {"event": AgentEvent.PIPELINE_STARTED})
    assert _row(engine, conversation).run_status == RunStatus.RUNNING
    await _drive(recorder, {"event": AgentEvent.MESSAGE_STOP}, {"event": AgentEvent.PIPELINE_FINISHED})
    assert _row(engine, conversation).run_status == RunStatus.IDLE


async def test_a_card_parks_the_run_and_the_stop_marker_after_it_does_not_unpark(engine, conversation):
    recorder = ConversationRecorder(conversation)
    await _drive(
        recorder,
        {"event": AgentEvent.PIPELINE_STARTED},
        {"event": AgentEvent.QUESTIONS_REQUIRED, "questions": [{"question": "Which market?"}]},
        {"event": AgentEvent.MESSAGE_STOP},
    )
    assert _row(engine, conversation).run_status == RunStatus.PAUSED
    # The answer arrives through the route, which records it: running again.
    await recorder.record_answer({"q": "Spain"})
    assert _row(engine, conversation).run_status == RunStatus.RUNNING


async def test_a_failed_turn_is_recorded_where_it_failed_with_its_code(engine, conversation):
    recorder = ConversationRecorder(conversation)
    await recorder.record_user("again")
    await _drive(
        recorder,
        {"event": AgentEvent.STEP_FAILED, "status": "error", "code": "auth", "retryable": False, "error": "The model provider rejected the API key."},
    )
    row = _row(engine, conversation)
    assert row.run_status == RunStatus.FAILED
    assert row.run_error == {"code": "auth", "retryable": False, "error": "The model provider rejected the API key."}
    assert _kinds(engine, conversation) == [EventKind.USER, EventKind.FAILURE]


async def test_a_step_that_fails_inside_a_running_pipeline_is_not_the_run_failing(engine, conversation):
    recorder = ConversationRecorder(conversation)
    await _drive(
        recorder,
        {"event": AgentEvent.PIPELINE_STARTED},
        {"event": AgentEvent.STEP_FAILED, "step_id": "crawl", "status": "error", "code": "network"},
    )
    assert _row(engine, conversation).run_status == RunStatus.RUNNING
    assert EventKind.FAILURE not in _kinds(engine, conversation)


async def test_a_run_failure_clears_on_the_next_successful_turn(engine, conversation):
    recorder = ConversationRecorder(conversation)
    await _drive(recorder, {"event": AgentEvent.PIPELINE_FAILED, "status": "error", "code": "rate_limited", "retryable": True, "error": "x"})
    assert _row(engine, conversation).run_error["code"] == "rate_limited"
    await recorder.record_user("try again")
    await _drive(recorder, {"event": AgentEvent.AGENT_MESSAGE_CHUNK, "text": "Sure"}, {"event": AgentEvent.MESSAGE_STOP})
    row = _row(engine, conversation)
    assert row.run_status == RunStatus.IDLE
    assert row.run_error is None


async def test_closing_mid_turn_is_a_cancellation_and_closing_idle_is_nothing(engine, conversation):
    recorder = ConversationRecorder(conversation)
    await _drive(recorder, {"event": AgentEvent.PIPELINE_STARTED})
    recorder.close()
    row = _row(engine, conversation)
    assert row.run_status == RunStatus.CANCELLED
    assert row.run_error["code"] == "cancelled"
    assert _kinds(engine, conversation) == [EventKind.FAILURE]

    idle = ConversationRecorder(conversation)
    await _drive(idle, {"event": AgentEvent.PIPELINE_STARTED}, {"event": AgentEvent.PIPELINE_FINISHED})
    idle.close()
    assert _row(engine, conversation).run_status == RunStatus.IDLE
    assert _kinds(engine, conversation) == [EventKind.FAILURE]  # no second one


async def test_a_replayed_pause_changes_nothing(engine, conversation):
    """A resumed session re-emits the card it is parked on; that is the same
    pause, already recorded as such."""
    recorder = ConversationRecorder(conversation)
    await _drive(recorder, {"event": AgentEvent.QUESTIONS_REQUIRED, "questions": [], "replay": True})
    assert _row(engine, conversation).run_status == RunStatus.IDLE  # the column default; nothing written


def test_the_list_summary_carries_the_run_fields():
    from types import SimpleNamespace

    from routes.agents import _conversation_summary

    conv = SimpleNamespace(
        id=uuid.uuid4(), agent_type="insights", project_id=uuid.uuid4(), mode="insights",
        artifact_type=None, artifact_id=None, title="t", status="active",
        run_status="failed", run_error={"code": "auth", "retryable": False, "error": "x"},
        pinned=False, last_seq=3, meta={}, created_at=None, last_active_at=None,
    )
    summary = _conversation_summary(conv)
    assert summary["run_status"] == "failed"
    assert summary["run_error"]["code"] == "auth"
