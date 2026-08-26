"""Tiered-autonomy policy + service core + GTM executor tests.

Covers the Phase-4 safety matrix: what may auto-apply (policy), that the
service actually auto-applies only clean agent-sourced sets on assisted
projects, and that the GTM publish executor records its rollback target
(the outgoing live version) before publishing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.auth import User  # noqa: E402
from models.execution import AUTONOMY_ASSISTED, AUTONOMY_MANUAL  # noqa: E402
from models.membership import ProjectMember  # noqa: E402
from models.project import Project  # noqa: E402
import service.execution.gtm_exec as gtm_exec  # noqa: E402
import service.execution.policy as policy  # noqa: E402
from service.execution.policy import change_auto_eligible, should_auto_apply  # noqa: E402
from service.execution.registry import (  # noqa: E402
    EXECUTOR_REGISTRY,
    ExecutorSpec,
    register_executor,
)
from service.execution.service import (  # noqa: E402
    StateError,
    apply_change_set,
    propose_change_set,
    rollback_change_set,
)
from service.membership import ROLE_OWNER  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def owner(db):
    user = User(email="policy-test@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, owner, autonomy):
    row = Project(user_id=owner.id, name="Policy Test", autonomy_level=autonomy)
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


class _CallLog:
    def __init__(self):
        self.applied: list[str] = []
        self.rolled_back: list[str] = []


@pytest.fixture
def fake_ops(monkeypatch):
    """Two executors on a test connector: one clean+reversible, one destructive."""
    log = _CallLog()

    def _preview(change, creds):
        return {"current": {"state": "before"}, "diff": "test diff", "warnings": []}

    def _apply(change, creds):
        log.applied.append(change["op_type"])
        return {"rollback": {"handle": "h1"}}

    def _rollback(change, creds):
        log.rolled_back.append(change["op_type"])
        return {"restored": True}

    safe = ExecutorSpec(
        op_type="testconn.safe",
        connector_type="testconn",
        label="Safe op",
        preview=_preview,
        apply=_apply,
        rollback=_rollback,
    )
    danger = ExecutorSpec(
        op_type="testconn.danger",
        connector_type="testconn",
        label="Dangerous op",
        preview=_preview,
        apply=_apply,
        rollback=_rollback,
        destructive=True,
    )
    register_executor(safe)
    register_executor(danger)
    monkeypatch.setattr(
        policy, "AUTO_APPLY_ALLOWLIST", policy.AUTO_APPLY_ALLOWLIST | {"testconn.safe"}
    )
    yield log
    EXECUTOR_REGISTRY.pop("testconn.safe", None)
    EXECUTOR_REGISTRY.pop("testconn.danger", None)


def _changes(*op_types):
    return [{"op_type": op, "summary": op, "target": {}, "payload": {}} for op in op_types]


# ---------------------------------------------------------------------------
# Policy matrix — change_auto_eligible
# ---------------------------------------------------------------------------

def _spec(op_type="google_ads.add_negative_keywords", destructive=False, rollback=True):
    return ExecutorSpec(
        op_type=op_type,
        connector_type=op_type.split(".")[0],
        label="x",
        preview=lambda c, k: {},
        apply=lambda c, k: {},
        rollback=(lambda c, k: {}) if rollback else None,
    ) if not destructive else ExecutorSpec(
        op_type=op_type,
        connector_type=op_type.split(".")[0],
        label="x",
        preview=lambda c, k: {},
        apply=lambda c, k: {},
        rollback=(lambda c, k: {}) if rollback else None,
        destructive=True,
    )


def test_clean_allowlisted_change_is_eligible():
    change = {"status": "proposed", "preview": {"diff": "x"}}
    assert change_auto_eligible(_spec(), change) is True


def test_off_allowlist_op_is_not_eligible():
    # Budget moves money — deliberately off the allowlist for now.
    change = {"status": "proposed", "preview": {"diff": "x"}}
    assert change_auto_eligible(_spec("google_ads.set_campaign_budget"), change) is False


def test_destructive_gate_is_absolute():
    change = {"status": "proposed", "preview": {"diff": "x"}}
    spec = _spec("google_ads.add_negative_keywords", destructive=True)
    assert change_auto_eligible(spec, change) is False


def test_no_rollback_means_not_eligible():
    change = {"status": "proposed", "preview": {"diff": "x"}}
    assert change_auto_eligible(_spec(rollback=False), change) is False


def test_guardrail_violation_blocks_eligibility():
    change = {"status": "blocked", "guardrail_violations": ["Never touch brand"], "preview": {}}
    assert change_auto_eligible(_spec(), change) is False


def test_preview_error_blocks_eligibility():
    change = {"status": "proposed", "preview": {"error": "API down"}}
    assert change_auto_eligible(_spec(), change) is False


# ---------------------------------------------------------------------------
# Policy matrix — should_auto_apply
# ---------------------------------------------------------------------------

def _proj(level):
    return Project(name="p", user_id=None, autonomy_level=level)  # type: ignore[arg-type]


def test_should_auto_apply_requires_all_conditions():
    eligible = [{"auto_eligible": True}, {"auto_eligible": True}]
    assert should_auto_apply(_proj(AUTONOMY_ASSISTED), "agent", eligible) is True


def test_user_source_never_auto_applies():
    assert should_auto_apply(_proj(AUTONOMY_ASSISTED), "user", [{"auto_eligible": True}]) is False


def test_manual_project_never_auto_applies():
    assert should_auto_apply(_proj(AUTONOMY_MANUAL), "agent", [{"auto_eligible": True}]) is False


def test_no_project_never_auto_applies():
    assert should_auto_apply(None, "agent", [{"auto_eligible": True}]) is False


def test_mixed_set_never_auto_applies():
    mixed = [{"auto_eligible": True}, {"auto_eligible": False}]
    assert should_auto_apply(_proj(AUTONOMY_ASSISTED), "agent", mixed) is False


def test_empty_set_never_auto_applies():
    assert should_auto_apply(_proj(AUTONOMY_ASSISTED), "agent", []) is False


# ---------------------------------------------------------------------------
# Service core — propose with autonomy
# ---------------------------------------------------------------------------

def test_agent_propose_on_assisted_project_auto_applies(db, owner, fake_ops):
    project = _project(db, owner, AUTONOMY_ASSISTED)
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="acct-1",
        account_name="Test",
        title="Safe changes",
        context="why",
        changes=_changes("testconn.safe", "testconn.safe"),
        creds={},
        project_id=project.id,
        agent_type="audit_seo",
        source="agent",
    )
    assert row.status == "applied"
    assert row.applied_by == "auto"
    assert row.auto_apply_eligible is True
    assert fake_ops.applied == ["testconn.safe", "testconn.safe"]
    assert all(c["status"] == "applied" for c in row.changes)
    assert row.changes[0]["result"]["rollback"] == {"handle": "h1"}


def test_mixed_set_with_destructive_waits_for_human(db, owner, fake_ops):
    project = _project(db, owner, AUTONOMY_ASSISTED)
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="acct-1",
        account_name="Test",
        title="Mixed changes",
        context="why",
        changes=_changes("testconn.safe", "testconn.danger"),
        creds={},
        project_id=project.id,
        agent_type="audit_seo",
        source="agent",
    )
    assert row.status == "proposed"
    assert row.applied_by == ""
    assert row.auto_apply_eligible is False
    assert fake_ops.applied == []
    # Per-change eligibility recorded for the review UI.
    by_op = {c["op_type"]: c["auto_eligible"] for c in row.changes}
    assert by_op == {"testconn.safe": True, "testconn.danger": False}


def test_manual_project_holds_even_clean_agent_sets(db, owner, fake_ops):
    project = _project(db, owner, AUTONOMY_MANUAL)
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="acct-1",
        account_name="Test",
        title="Safe changes",
        context="why",
        changes=_changes("testconn.safe"),
        creds={},
        project_id=project.id,
        source="agent",
    )
    assert row.status == "proposed"
    assert row.auto_apply_eligible is True  # eligible, but autonomy says wait
    assert fake_ops.applied == []


def test_user_source_never_auto_applies_in_service(db, owner, fake_ops):
    project = _project(db, owner, AUTONOMY_ASSISTED)
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="acct-1",
        account_name="Test",
        title="Safe changes",
        context="why",
        changes=_changes("testconn.safe"),
        creds={},
        project_id=project.id,
        source="user",
    )
    assert row.status == "proposed"
    assert fake_ops.applied == []


def test_wrong_connector_op_rejected(db, owner, fake_ops):
    with pytest.raises(ValueError, match="belongs to connector"):
        propose_change_set(
            db,
            user_id=owner.id,
            connector_type="ga4",
            account_id="",
            account_name="",
            title="t",
            context="",
            changes=_changes("testconn.safe"),
            creds={},
        )


def test_rollback_after_auto_apply(db, owner, fake_ops):
    project = _project(db, owner, AUTONOMY_ASSISTED)
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="acct-1",
        account_name="Test",
        title="Safe changes",
        context="why",
        changes=_changes("testconn.safe"),
        creds={},
        project_id=project.id,
        source="agent",
    )
    assert row.status == "applied"
    row = rollback_change_set(db, row, {})
    assert row.status == "rolled_back"
    assert fake_ops.rolled_back == ["testconn.safe"]


def test_apply_requires_approved_status(db, owner, fake_ops):
    project = _project(db, owner, AUTONOMY_MANUAL)
    row = propose_change_set(
        db,
        user_id=owner.id,
        connector_type="testconn",
        account_id="acct-1",
        account_name="Test",
        title="Safe changes",
        context="why",
        changes=_changes("testconn.safe"),
        creds={},
        project_id=project.id,
        source="agent",
    )
    with pytest.raises(StateError, match="approved before applying"):
        apply_change_set(db, row, {})


# ---------------------------------------------------------------------------
# GTM executors — publish records its rollback target first
# ---------------------------------------------------------------------------

class _Call:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeTags:
    def __init__(self, gtm):
        self._gtm = gtm

    def list(self, parent):
        return _Call({"tag": list(self._gtm.tags.values())})

    def create(self, parent, body):
        path = f"{parent}/tags/{len(self._gtm.tags) + 1}"
        stored = dict(body, path=path)
        self._gtm.tags[body["name"]] = stored
        self._gtm.log.append(("create_tag", path))
        return _Call(stored)

    def update(self, path, body):
        stored = dict(body, path=path)
        self._gtm.tags[body["name"]] = stored
        self._gtm.log.append(("update_tag", path))
        return _Call(stored)

    def delete(self, path):
        self._gtm.log.append(("delete_tag", path))
        self._gtm.tags = {n: t for n, t in self._gtm.tags.items() if t["path"] != path}
        return _Call({})


class _FakeWorkspaces:
    def __init__(self, gtm):
        self._gtm = gtm

    def list(self, parent):
        return _Call({"workspace": [
            {"name": "Default Workspace", "path": f"{parent}/workspaces/1"},
        ]})

    def tags(self):
        return _FakeTags(self._gtm)

    def variables(self):
        return _FakeTags(self._gtm)

    def create_version(self, path, body):
        version_id = self._gtm.next_version_id
        self._gtm.next_version_id += 1
        container = "/".join(path.split("/")[:4])
        self._gtm.log.append(("create_version", path, body.get("name", "")))
        return _Call({
            "containerVersion": {
                "path": f"{container}/versions/{version_id}",
                "containerVersionId": str(version_id),
            }
        })


class _FakeVersions:
    def __init__(self, gtm):
        self._gtm = gtm

    def live(self, parent):
        if self._gtm.live_version_id is None:
            from googleapiclient.errors import HttpError

            resp = type("R", (), {"status": 404, "reason": "not found"})()
            return _Call(HttpError(resp, b"no live version"))
        return _Call({"containerVersionId": self._gtm.live_version_id})

    def publish(self, path):
        version_id = path.rsplit("/", 1)[-1]
        self._gtm.live_version_id = version_id
        self._gtm.log.append(("publish", path))
        return _Call({"containerVersion": {"containerVersionId": version_id, "path": path}})


class _FakeContainers:
    def __init__(self, gtm):
        self._gtm = gtm

    def workspaces(self):
        return _FakeWorkspaces(self._gtm)

    def versions(self):
        return _FakeVersions(self._gtm)


class _FakeGTM:
    """Chained googleapiclient stand-in for tagmanager v2."""

    def __init__(self, live_version_id="7"):
        self.live_version_id = live_version_id
        self.tags: dict = {}
        self.next_version_id = 8
        self.log: list = []

    def accounts(self):
        return self

    def containers(self):
        return _FakeContainers(self)


_CONTAINER = "accounts/11/containers/22"
_CREDS = {"client_id": "c", "client_secret": "s", "refresh_token": "r"}


@pytest.fixture
def fake_gtm(monkeypatch):
    fake = _FakeGTM()
    monkeypatch.setattr(gtm_exec, "build_gtm_service", lambda creds: fake)
    return fake


def test_gtm_publish_preview_records_live_version(fake_gtm):
    change = {"op_type": "gtm.publish_version", "target": {"container_path": _CONTAINER}, "payload": {}}
    preview = gtm_exec._publish_preview(change, _CREDS)
    assert preview["current"]["live_version_id"] == "7"
    assert preview["current"]["workspace_path"] == f"{_CONTAINER}/workspaces/1"
    assert "PUBLISH" in preview["diff"]


def test_gtm_publish_apply_records_rollback_target_then_publishes(fake_gtm):
    change = {
        "op_type": "gtm.publish_version",
        "target": {"container_path": _CONTAINER},
        "payload": {"name": "Duct release"},
        "current": {"workspace_path": f"{_CONTAINER}/workspaces/1", "live_version_id": "7"},
    }
    result = gtm_exec._publish_apply(change, _CREDS)
    assert result["rollback"]["prior_live_version_id"] == "7"
    assert result["published_version_id"] == "8"
    # Version creation happened before the publish.
    ops = [entry[0] for entry in fake_gtm.log]
    assert ops.index("create_version") < ops.index("publish")
    assert fake_gtm.live_version_id == "8"


def test_gtm_publish_rollback_republishes_prior_version(fake_gtm):
    change = {
        "op_type": "gtm.publish_version",
        "result": {"rollback": {"container_path": _CONTAINER, "prior_live_version_id": "7"}},
    }
    result = gtm_exec._publish_rollback(change, _CREDS)
    assert result["republished_version_id"] == "7"
    assert ("publish", f"{_CONTAINER}/versions/7") in fake_gtm.log
    assert fake_gtm.live_version_id == "7"


def test_gtm_publish_rollback_without_prior_version_refuses(fake_gtm):
    change = {
        "op_type": "gtm.publish_version",
        "result": {"rollback": {"container_path": _CONTAINER, "prior_live_version_id": ""}},
    }
    with pytest.raises(ValueError, match="no live version"):
        gtm_exec._publish_rollback(change, _CREDS)


def test_gtm_first_publish_has_empty_rollback_target(fake_gtm):
    fake_gtm.live_version_id = None  # never published
    change = {
        "op_type": "gtm.publish_version",
        "target": {"container_path": _CONTAINER},
        "payload": {},
    }
    preview = gtm_exec._publish_preview(change, _CREDS)
    assert preview["current"]["live_version_id"] == ""
    assert any("no live version" in w for w in preview["warnings"])


def test_gtm_upsert_tag_creates_then_rollback_deletes(fake_gtm):
    change = {
        "op_type": "gtm.upsert_tag",
        "target": {"container_path": _CONTAINER},
        "payload": {"tag": {"name": "GA4 Config", "type": "gaawe"}},
    }
    preview = gtm_exec._upsert_preview("tag")(change, _CREDS)
    assert preview["current"]["exists"] is False
    assert preview["diff"].startswith("Create tag")

    change["current"] = preview["current"]
    result = gtm_exec._upsert_apply("tag")(change, _CREDS)
    assert result["rollback"]["delete_path"]

    change["result"] = result
    rolled = gtm_exec._upsert_rollback("tag")(change, _CREDS)
    assert rolled["deleted"] == result["rollback"]["delete_path"]
    assert fake_gtm.tags == {}


def test_gtm_upsert_tag_updates_then_rollback_restores(fake_gtm):
    prior = {"name": "GA4 Config", "type": "gaawe", "path": f"{_CONTAINER}/workspaces/1/tags/1"}
    fake_gtm.tags["GA4 Config"] = prior
    change = {
        "op_type": "gtm.upsert_tag",
        "target": {"workspace_path": f"{_CONTAINER}/workspaces/1"},
        "payload": {"tag": {"name": "GA4 Config", "type": "gaawe", "notes": "v2"}},
    }
    result = gtm_exec._upsert_apply("tag")(change, _CREDS)
    assert result["rollback"]["restore_path"] == prior["path"]
    assert result["rollback"]["restore_body"]["name"] == "GA4 Config"

    change["result"] = result
    rolled = gtm_exec._upsert_rollback("tag")(change, _CREDS)
    assert rolled["restored"] == prior["path"]
    # The restore re-applied the prior body (no "notes").
    assert "notes" not in fake_gtm.tags["GA4 Config"] or fake_gtm.tags["GA4 Config"].get("notes") != "v2"


def test_gtm_rollback_to_version_records_outgoing_live(fake_gtm):
    change = {
        "op_type": "gtm.rollback_to_version",
        "target": {"container_path": _CONTAINER},
        "payload": {"version_id": "5"},
    }
    result = gtm_exec._rollback_to_apply(change, _CREDS)
    assert result["rollback"]["prior_live_version_id"] == "7"
    assert result["published_version_id"] == "5"
    assert fake_gtm.live_version_id == "5"


# ---------------------------------------------------------------------------
# Registry hygiene — new wave-1 executors
# ---------------------------------------------------------------------------

def test_wave1_executors_registered():
    import service.execution.ga4_exec  # noqa: F401
    import service.execution.google_ads_exec  # noqa: F401

    expected = {
        "google_ads.set_campaign_budget",
        "google_ads.set_campaign_bidding",
        "google_ads.add_keywords",
        "google_ads.set_keyword_status",
        "google_ads.set_ad_group_status",
        "google_ads.set_campaign_status",
        "ga4.create_audience",
        "ga4.archive_audience",
        "ga4.create_google_ads_link",
        "ga4.delete_google_ads_link",
        "gtm.upsert_tag",
        "gtm.upsert_variable",
        "gtm.publish_version",
        "gtm.rollback_to_version",
    }
    assert expected <= set(EXECUTOR_REGISTRY)
    destructive = {op for op in expected if EXECUTOR_REGISTRY[op].destructive}
    assert destructive == {
        "ga4.archive_audience",
        "ga4.delete_google_ads_link",
        "gtm.publish_version",
        "gtm.rollback_to_version",
    }
    # Everything on the auto-apply allowlist must be registered, reversible,
    # and non-destructive.
    for op in policy.AUTO_APPLY_ALLOWLIST:
        spec = EXECUTOR_REGISTRY[op]
        assert spec.rollback is not None
        assert spec.destructive is False
