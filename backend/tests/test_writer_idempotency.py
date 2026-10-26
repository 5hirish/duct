"""A writer executed twice for one tool call writes once.

A run cut between a tool's commit and its superstep checkpoint is continued
from the checkpoint, and the checkpoint executes the same call again, with
the same call id. ProposeChanges and the artifact writers key on that id
(agents/core/tool_calls.py); RememberFact already lands a duplicate on the
existing row by content hash (service/memory.py), so it is not repeated here.
"""
from __future__ import annotations

import uuid
from contextlib import nullcontext

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

import service.artifact_store as store
from agents.core import artifact_tools
from agents.core.tool_calls import current_tool_call_id, executing_tool_call
from agents.tools import execution_tools
from models.artifact import Artifact
from models.auth import User
from models.execution import AUTONOMY_MANUAL, ExecutionChangeSet
from models.membership import ProjectMember
from models.project import Project
from service.artifact_store import create_artifact_group, revise_artifact
from service.execution.registry import EXECUTOR_REGISTRY, ExecutorSpec, register_executor
from service.execution.service import propose_change_set
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

CONNECTOR = "idemconn"
OP = "idemconn.add"


@pytest.fixture
def engine(monkeypatch):
    engine = make_sqlite_engine()

    def _fake_db():
        yield Session(engine)

    # The persister opens its own session; the tools' threads open one too.
    monkeypatch.setattr(store, "db_session", _fake_db)
    monkeypatch.setattr("db.session.get_session", _fake_db)
    monkeypatch.setattr(store, "put_private", lambda key, data, content_type: key)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def project(db):
    user = User(email="idempotency@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    row = Project(user_id=user.id, name="Idempotency", autonomy_level=AUTONOMY_MANUAL)
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=user.id, role=ROLE_OWNER))
    db.commit()
    return row


@pytest.fixture
def previews():
    """A fake connector that counts how often the account was read."""
    calls: list[dict] = []

    def _preview(change, creds):
        calls.append(change)
        return {"current": {}, "diff": "d"}

    register_executor(ExecutorSpec(
        op_type=OP, connector_type=CONNECTOR, label=OP,
        preview=_preview, apply=lambda c, k: {"rollback": {}}, rollback=lambda c, k: {}, drift_keys=(),
    ))
    yield calls
    EXECUTOR_REGISTRY.pop(OP, None)


def _propose(db, project, *, conversation_id, tool_call_id):
    return propose_change_set(
        db, user_id=project.user_id, connector_type=CONNECTOR, account_id="a1",
        account_name="A", title="t", context="",
        changes=[{"op_type": OP, "summary": OP}],
        creds={}, project_id=project.id, conversation_id=conversation_id,
        agent_type="insights", source="agent", tool_call_id=tool_call_id,
    )


def _sets(db) -> list[ExecutionChangeSet]:
    return list(db.exec(select(ExecutionChangeSet)))


# --- change sets -----------------------------------------------------------

def test_a_replayed_proposal_returns_the_set_it_already_proposed(db, project, previews):
    cid = uuid.uuid4()
    first = _propose(db, project, conversation_id=cid, tool_call_id="call_1")
    again = _propose(db, project, conversation_id=cid, tool_call_id="call_1")
    assert again.id == first.id
    assert len(_sets(db)) == 1
    # The replay did not read the account again either.
    assert len(previews) == 1


def test_each_call_proposes_its_own_set(db, project, previews):
    cid = uuid.uuid4()
    a = _propose(db, project, conversation_id=cid, tool_call_id="call_1")
    b = _propose(db, project, conversation_id=cid, tool_call_id="call_2")
    assert a.id != b.id and len(_sets(db)) == 2


def test_a_proposal_without_a_call_is_never_folded(db, project, previews):
    """Sets proposed from the browser carry no call id; two of them in one
    conversation are two sets, which is also what proves the index is
    partial on SQLite."""
    cid = uuid.uuid4()
    _propose(db, project, conversation_id=cid, tool_call_id="")
    _propose(db, project, conversation_id=cid, tool_call_id="")
    assert len(_sets(db)) == 2


def test_the_index_holds_a_second_row_for_one_call_even_past_the_lookup(db, project):
    cid = uuid.uuid4()
    for _ in range(2):
        db.add(ExecutionChangeSet(
            user_id=project.user_id, project_id=project.id, conversation_id=cid,
            tool_call_id="call_x", connector_type=CONNECTOR, title="t", changes=[],
        ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --- artifacts -------------------------------------------------------------

def _versions(db) -> list[Artifact]:
    return list(db.exec(select(Artifact).order_by(Artifact.version)))


def test_a_replayed_create_hands_back_the_group_it_minted(db, project):
    cid = uuid.uuid4()
    kw = dict(
        project_id=project.id, user_id=project.user_id, agent_type="insights", kind="memo",
        content_type="text/markdown", title="Plan", content="# Plan", slug="plan",
        conversation_id=cid, tool_call_id="call_1",
    )
    first = create_artifact_group(db, **kw)
    again = create_artifact_group(db, **kw)
    assert again.id == first.id
    assert len(_versions(db)) == 1


def test_a_replayed_revision_appends_one_version_not_two(db, project):
    cid = uuid.uuid4()
    head = create_artifact_group(
        db, project_id=project.id, user_id=project.user_id, agent_type="insights", kind="memo",
        content_type="text/markdown", title="Plan", content="# Plan", slug="plan",
        conversation_id=cid, tool_call_id="call_1",
    )
    v2 = revise_artifact(db, head, content="# Plan v2", conversation_id=cid, tool_call_id="call_2")
    # The replay would otherwise fail the version check too: the head has moved.
    again = revise_artifact(
        db, head, content="# Plan v2", expected_version=1, conversation_id=cid, tool_call_id="call_2",
    )
    assert again.id == v2.id
    assert [v.version for v in _versions(db)] == [1, 2]


# --- the tools hand the call to their service -------------------------------

async def test_propose_changes_passes_the_executing_call(monkeypatch):
    seen: dict = {}

    def _fake_propose_sync(args, **kw):
        seen.update(kw)
        raise ValueError("stop here")

    monkeypatch.setattr(execution_tools, "_propose_sync", _fake_propose_sync)
    with executing_tool_call("call_7"):
        await execution_tools._propose(
            {"connector_type": CONNECTOR, "changes": [{"op_type": OP}]},
            user_id=uuid.uuid4(), project_id=uuid.uuid4(), conversation_id=uuid.uuid4(),
            agent_type="insights", connector_types=(CONNECTOR,), on_change_set=None,
        )
    assert seen["tool_call_id"] == "call_7"


async def test_create_artifact_passes_the_executing_call(monkeypatch):
    seen: dict = {}

    def _fake_create(db, **kw):
        seen.update(kw)
        raise ValueError("stop here")

    monkeypatch.setattr(store, "create_artifact_group", _fake_create)
    monkeypatch.setattr("db.session.get_session", lambda: iter([nullcontext()]))
    tools = {t.name: t for t in artifact_tools.build_artifact_tools_lc(uuid.uuid4(), user_id=uuid.uuid4())}
    with executing_tool_call("call_9"):
        await tools["CreateArtifact"].ainvoke(
            {"slug": "plan", "title": "Plan", "content_type": "text/markdown", "content": "# Plan"}
        )
    assert seen["tool_call_id"] == "call_9"


def test_outside_a_tool_call_there_is_no_id():
    assert current_tool_call_id() == ""
    with executing_tool_call("call_1"):
        assert current_tool_call_id() == "call_1"
    assert current_tool_call_id() == ""
