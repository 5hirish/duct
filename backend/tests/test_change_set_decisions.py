"""The agent hears what the person did on its review cards.

A proposing agent is told to wait and not poll, so an approve or reject made on
the card lives only in the execution log. The next message the person sends
carries every such decision made since their previous one, and nothing else.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session

import routes.agents as agents_routes
from agents.content.persistence import append_event, last_user_turn_at
from models.activity import ActivityLog
from models.auth import User
from models.content.conversation import AgentConversation
from models.project import Project
from tests.conftest import make_sqlite_engine


@pytest.fixture
def engine(monkeypatch):
    engine = make_sqlite_engine()

    def _fake_db():
        yield Session(engine)

    monkeypatch.setattr(agents_routes, "db_session", _fake_db)
    return engine


@pytest.fixture
def conversation(engine):
    with Session(engine) as db:
        user = User(email="decisions@example.com")
        db.add(user)
        db.commit()
        project = Project(user_id=user.id, name="Decisions")
        db.add(project)
        db.commit()
        conv = AgentConversation(agent_type="insights", project_id=project.id)
        db.add(conv)
        db.commit()
        return SimpleNamespace(id=conv.id)


def _log(db, conversation_id, action, summary, at, source="user"):
    db.add(ActivityLog(
        category="execution", action=action, source=source, conversation_id=conversation_id,
        target_type="change_set", target_id="cs-1", summary=summary, created_at=at,
    ))
    db.commit()


def test_only_the_persons_decisions_since_their_last_message(engine, conversation):
    with Session(engine) as db:
        append_event(db, conversation.id, "user", {"content": "pause display?"})
        said_at = last_user_turn_at(db, conversation.id)
        _log(db, conversation.id, "change_set.approved", "Approved “Old set”", said_at - timedelta(minutes=5))
        _log(db, conversation.id, "change_set.rejected", "Rejected “Pause Display”", said_at + timedelta(minutes=1))
        _log(db, conversation.id, "change_set.rolled_back", "Rolled back by the agent", said_at + timedelta(minutes=2), source="agent")
        _log(db, None, "change_set.rejected", "Another thread", said_at + timedelta(minutes=3))

    block = agents_routes._decisions_block(SimpleNamespace(conversation_id=conversation.id))
    assert block.startswith("<change_set_decisions>")
    assert "Rejected “Pause Display”" in block
    for absent in ("Old set", "by the agent", "Another thread"):
        assert absent not in block


def test_a_thread_with_no_decisions_adds_nothing(engine, conversation):
    assert agents_routes._decisions_block(SimpleNamespace(conversation_id=conversation.id)) == ""
    assert agents_routes._decisions_block(SimpleNamespace(conversation_id=None)) == ""


def test_a_plan_accepted_on_the_pane_reaches_the_next_message(engine, conversation):
    """Accept sends no message (it used to send "Carry on", and the agent went
    on to draft posts in the plan's pane), so the next turn is told instead."""
    from models.content.conversation import AgentEvent as AgentEventRow

    with Session(engine) as db:
        append_event(db, conversation.id, "user", {"content": "make it all slideshows"})
        said_at = last_user_turn_at(db, conversation.id)
        for seq, (decision, name, at) in enumerate([
            ("rejected", "October plan", said_at - timedelta(minutes=5)),
            ("accepted", "November plan", said_at + timedelta(minutes=1)),
        ], start=10):
            db.add(AgentEventRow(conversation_id=conversation.id, seq=seq, kind="plan_decision",
                                 data={"decision": decision, "name": name}, created_at=at))
        db.commit()

    block = agents_routes._decisions_block(SimpleNamespace(conversation_id=conversation.id))
    assert block.startswith("<plan_decisions>")
    assert 'accepted "November plan"' in block and "October plan" not in block
