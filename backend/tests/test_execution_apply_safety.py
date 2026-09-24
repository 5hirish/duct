"""An approval means exactly what the person saw, applied exactly once.

Two failures this pins: two requests racing on one approved set (a double
click, a second tab, a click racing auto-apply) both running the executors,
and an approval applied after the account moved underneath it (approve
"budget 50 → 60", someone raises it to 80, apply cuts it to 60).
"""

from __future__ import annotations

import pytest
from sqlmodel import Session

from models.auth import User
from models.execution import AUTONOMY_MANUAL, ExecutionChangeSet
from models.membership import ProjectMember
from models.project import Project
from service.execution.registry import EXECUTOR_REGISTRY, ExecutorSpec, register_executor
from service.execution.service import (
    StateError,
    apply_change_set,
    claim_transition,
    propose_change_set,
)
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine
from utils.dates import utcnow


@pytest.fixture
def engine():
    return make_sqlite_engine()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def project(db):
    user = User(email="apply-safety@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    row = Project(user_id=user.id, name="Apply safety", autonomy_level=AUTONOMY_MANUAL)
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=user.id, role=ROLE_OWNER))
    db.commit()
    return row


class _Account:
    """A fake remote account: one budget, and a log of every apply."""

    def __init__(self):
        self.budget = 50
        self.applied: list[str] = []
        self.fail_preview = False


@pytest.fixture
def account():
    acct = _Account()

    def _preview(change, creds):
        if acct.fail_preview:
            raise RuntimeError("upstream 503")
        return {"current": {"budget": acct.budget, "unrelated_count": len(acct.applied)}, "diff": "d"}

    def _apply(change, creds):
        acct.applied.append(change["op_type"])
        return {"rollback": {}}

    for op, keys in (("safetyconn.set_budget", ("budget",)), ("safetyconn.add", ())):
        register_executor(ExecutorSpec(
            op_type=op, connector_type="safetyconn", label=op,
            preview=_preview, apply=_apply, rollback=lambda c, k: {}, drift_keys=keys,
        ))
    yield acct
    EXECUTOR_REGISTRY.pop("safetyconn.set_budget", None)
    EXECUTOR_REGISTRY.pop("safetyconn.add", None)


def _approved(db, project, *op_types) -> ExecutionChangeSet:
    row = propose_change_set(
        db, user_id=project.user_id, connector_type="safetyconn", account_id="a1",
        account_name="A", title="t", context="",
        changes=[{"op_type": op, "summary": op} for op in op_types],
        creds={}, project_id=project.id, source="user",
    )
    changes = [{**c, "status": "approved"} for c in row.changes]
    assert claim_transition(db, row, from_statuses=("proposed",), changes=changes, status="approved",
                            approved_at=utcnow(), updated_at=utcnow())
    return row


def test_two_requests_on_one_approval_apply_once(engine, db, project, account):
    row = _approved(db, project, "safetyconn.set_budget")
    # The second request read the row while it was still "approved".
    with Session(engine) as other:
        stale = other.get(ExecutionChangeSet, row.id)
        assert stale.status == "approved"
        apply_change_set(db, row, {})
        with pytest.raises(StateError, match="another request got to it first"):
            apply_change_set(other, stale, {})
    assert account.applied == ["safetyconn.set_budget"]


def test_a_late_approve_cannot_reset_a_set_that_is_running(db, project, account):
    row = _approved(db, project, "safetyconn.set_budget")
    assert claim_transition(db, row, from_statuses=("approved",), status="applying")
    assert not claim_transition(db, row, from_statuses=("proposed", "approved"), status="approved")
    assert row.status == "applying"


def test_a_change_that_moved_since_approval_is_held_back(db, project, account):
    row = _approved(db, project, "safetyconn.set_budget", "safetyconn.add")
    account.budget = 80  # raised by someone else between approve and apply
    row = apply_change_set(db, row, {})
    by_op = {c["op_type"]: c for c in row.changes}
    assert by_op["safetyconn.set_budget"]["status"] == "blocked"
    assert by_op["safetyconn.set_budget"]["drift"] == {"budget": {"approved": 50, "now": 80}}
    # The additive op declares no drift keys: its snapshot moving is not a reason to stop.
    assert by_op["safetyconn.add"]["status"] == "applied"
    assert account.applied == ["safetyconn.add"]


def test_an_unreadable_target_is_not_applied_blind(db, project, account):
    row = _approved(db, project, "safetyconn.set_budget")
    account.fail_preview = True
    row = apply_change_set(db, row, {})
    assert row.changes[0]["status"] == "blocked"
    assert "upstream 503" in row.changes[0]["drift"]["error"]
    assert account.applied == []


def test_an_unchanged_target_applies(db, project, account):
    row = _approved(db, project, "safetyconn.set_budget")
    row = apply_change_set(db, row, {})
    assert row.status == "applied"
    assert account.applied == ["safetyconn.set_budget"]
