"""Per-project connector bindings — resolution order + binding routes.

Covers the agency shape: project A bills through Stripe account X, project B
through Y. Bindings reference credential rows (never copy secrets), win over
the caller's user-level rows during resolution, and are membership-gated.
"""

from __future__ import annotations


import pytest

from tests.conftest import make_sqlite_engine
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

from config import Configs
from db.session import get_session as get_session_dep
from models.activity import ActivityLog
from models.auth import User
from models.connector import ConnectorCredential, ProjectConnector
from models.membership import ProjectMember, ROLE_COLLABORATOR
from models.project import Project
import routes.project_connectors as pc_routes
import routes.user_connectors as uc_routes
import service.auth as auth_service
import service.credentials as credentials_service
import service.execution.creds as creds_module
from service.connector_access import stored_connector_credentials
from service.execution.creds import resolve_execution_creds
from service.membership import ROLE_OWNER

FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
def engine():
    engine = make_sqlite_engine(drop_partial_indexes=True)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def cfg(monkeypatch):
    config = Configs(
        credentials_encryption_key=FERNET_KEY,
        google_ads_developer_token="env-dev-token",
        google_oauth_client_id="env-client-id",
        google_oauth_client_secret="env-client-secret",
    )
    monkeypatch.setattr(creds_module, "get_configs", lambda: config)
    monkeypatch.setattr(credentials_service, "get_configs", lambda: config)
    return config


@pytest.fixture
def owner(db):
    user = User(email="pc-owner@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def collaborator(db):
    user = User(email="pc-collab@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def project(db, owner, collaborator):
    row = Project(user_id=owner.id, name="Client A")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.add(
        ProjectMember(
            project_id=row.id, user_id=collaborator.id, role=ROLE_COLLABORATOR
        )
    )
    db.commit()
    return row


def _store(db, user, connector_type, account_id, data, account_name=""):
    row = ConnectorCredential(
        user_id=user.id,
        connector_type=connector_type,
        account_id=account_id,
        account_name=account_name,
        credentials_enc=credentials_service.encrypt_credentials(data),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _bind(db, project, cred, user):
    row = ProjectConnector(
        project_id=project.id,
        connector_type=cred.connector_type,
        connector_credential_id=cred.id,
        created_by_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Resolution order
# ---------------------------------------------------------------------------

def test_binding_wins_over_user_default_row(db, cfg, owner, project):
    _store(db, owner, "stripe", "", {"api_key": "rk_default"})
    bound = _store(db, owner, "stripe", "acct_B", {"api_key": "rk_project_b"})
    _bind(db, project, bound, owner)

    assert stored_connector_credentials(db, owner.id, "stripe") == {"api_key": "rk_default"}
    assert stored_connector_credentials(
        db, owner.id, "stripe", project_id=project.id
    ) == {"api_key": "rk_project_b"}


def test_collaborator_uses_projects_bound_account(db, cfg, owner, collaborator, project):
    # The binding references the OWNER's credential row; a collaborator's
    # project-scoped run resolves through it — the project's account is the
    # project's account. (Membership is checked by every caller that passes
    # project_id.)
    bound = _store(db, owner, "google_ads", "111", {"refresh_token": "owner-rt"})
    _bind(db, project, bound, owner)

    creds = resolve_execution_creds(
        db, collaborator.id, "google_ads", project_id=project.id
    )
    assert creds["refresh_token"] == "owner-rt"
    # Without the project scope the collaborator has nothing.
    assert resolve_execution_creds(db, collaborator.id, "google_ads")["refresh_token"] == ""


def test_explicit_other_account_skips_binding(db, cfg, owner, project):
    bound = _store(db, owner, "google_ads", "111", {"refresh_token": "bound-rt"})
    _bind(db, project, bound, owner)
    _store(db, owner, "google_ads", "222", {"refresh_token": "other-rt"})

    creds = resolve_execution_creds(
        db, owner.id, "google_ads", account_id="222", project_id=project.id
    )
    assert creds["refresh_token"] == "other-rt"


def test_unbound_project_falls_back_to_user_rows(db, cfg, owner, project):
    _store(db, owner, "revenuecat", "", {"api_key": "sk_user"})
    assert stored_connector_credentials(
        db, owner.id, "revenuecat", project_id=project.id
    ) == {"api_key": "sk_user"}


def test_account_agnostic_binding_applies_to_any_account(db, cfg, owner, project):
    # A binding to an account-agnostic row (account_id="") serves whatever
    # account the change set targets — e.g. one Google login spanning several
    # customer ids.
    bound = _store(db, owner, "google_ads", "", {"refresh_token": "generic-rt"})
    _bind(db, project, bound, owner)
    creds = resolve_execution_creds(
        db, owner.id, "google_ads", account_id="999", project_id=project.id
    )
    assert creds["refresh_token"] == "generic-rt"


# ---------------------------------------------------------------------------
# Binding routes
# ---------------------------------------------------------------------------

def _make_client(db, user):
    app = FastAPI()
    app.include_router(pc_routes.router, prefix="/api/user/projects")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app)


def test_bind_list_rebind_unbind_roundtrip(db, cfg, owner, project):
    cred_a = _store(db, owner, "stripe", "acct_A", {"api_key": "rk_a"}, account_name="Client A")
    cred_b = _store(db, owner, "stripe", "acct_B", {"api_key": "rk_b"}, account_name="Client B")
    client = _make_client(db, owner)

    res = client.put(
        f"/api/user/projects/{project.id}/connectors/stripe",
        json={"connector_credential_id": str(cred_a.id)},
    )
    assert res.status_code == 200
    assert res.json()["account_name"] == "Client A"

    listed = client.get(f"/api/user/projects/{project.id}/connectors").json()
    assert [r["connector_type"] for r in listed] == ["stripe"]

    # Rebinding the same connector type replaces the mapping, never duplicates.
    res = client.put(
        f"/api/user/projects/{project.id}/connectors/stripe",
        json={"connector_credential_id": str(cred_b.id)},
    )
    assert res.status_code == 200
    assert res.json()["account_name"] == "Client B"
    rows = db.execute(select(ProjectConnector)).scalars().all()
    assert len(rows) == 1 and rows[0].connector_credential_id == cred_b.id

    assert client.delete(f"/api/user/projects/{project.id}/connectors/stripe").status_code == 204
    assert client.delete(f"/api/user/projects/{project.id}/connectors/stripe").status_code == 404


def test_binding_requires_membership(db, cfg, owner, project):
    stranger = User(email="pc-stranger@example.com")
    db.add(stranger)
    db.commit()
    db.refresh(stranger)
    cred = _store(db, stranger, "stripe", "acct_S", {"api_key": "rk_s"})
    client = _make_client(db, stranger)

    assert client.get(f"/api/user/projects/{project.id}/connectors").status_code == 404
    res = client.put(
        f"/api/user/projects/{project.id}/connectors/stripe",
        json={"connector_credential_id": str(cred.id)},
    )
    assert res.status_code == 404


def test_cannot_bind_someone_elses_credential(db, cfg, owner, collaborator, project):
    owners_cred = _store(db, owner, "stripe", "acct_A", {"api_key": "rk_a"})
    client = _make_client(db, collaborator)
    res = client.put(
        f"/api/user/projects/{project.id}/connectors/stripe",
        json={"connector_credential_id": str(owners_cred.id)},
    )
    assert res.status_code == 404  # foreign credential ids stay unconfirmed

    # Their own credential binds fine — collaborators may offer their accounts.
    own = _store(db, collaborator, "stripe", "acct_C", {"api_key": "rk_c"})
    res = client.put(
        f"/api/user/projects/{project.id}/connectors/stripe",
        json={"connector_credential_id": str(own.id)},
    )
    assert res.status_code == 200


def test_connector_type_mismatch_rejected(db, cfg, owner, project):
    cred = _store(db, owner, "stripe", "acct_A", {"api_key": "rk_a"})
    client = _make_client(db, owner)
    res = client.put(
        f"/api/user/projects/{project.id}/connectors/revenuecat",
        json={"connector_credential_id": str(cred.id)},
    )
    assert res.status_code == 422
    res = client.put(
        f"/api/user/projects/{project.id}/connectors/not_a_connector",
        json={"connector_credential_id": str(cred.id)},
    )
    assert res.status_code == 422


def test_bind_unbind_write_activity_rows(db, cfg, owner, project):
    cred = _store(db, owner, "meta_ads", "act_1", {"access_token": "EAA"}, account_name="Meta A")
    client = _make_client(db, owner)
    client.put(
        f"/api/user/projects/{project.id}/connectors/meta_ads",
        json={"connector_credential_id": str(cred.id)},
    )
    client.delete(f"/api/user/projects/{project.id}/connectors/meta_ads")
    actions = [
        r.action
        for r in db.execute(select(ActivityLog).order_by(ActivityLog.created_at)).scalars()
    ]
    assert actions == ["project_connector.bound", "project_connector.unbound"]
    bound_row = db.execute(
        select(ActivityLog).where(ActivityLog.action == "project_connector.bound")
    ).scalars().one()
    assert bound_row.project_id == project.id
    assert bound_row.connector_type == "meta_ads"
    assert "Meta A" in bound_row.summary


def test_unknown_binding_ids_do_not_break_resolution(db, cfg, owner, project):
    # A binding whose credential row was deleted (Postgres cascades; SQLite in
    # tests does not) must degrade to user-level resolution, never raise.
    cred = _store(db, owner, "stripe", "acct_A", {"api_key": "rk_a"})
    _bind(db, project, cred, owner)
    db.delete(cred)
    db.commit()
    _store(db, owner, "stripe", "", {"api_key": "rk_fallback"})
    assert stored_connector_credentials(
        db, owner.id, "stripe", project_id=project.id
    ) == {"api_key": "rk_fallback"}


# ---------------------------------------------------------------------------
# Data-source inventory routes
#
# The counting question ("has this account connected anything at all?") is not
# the binding question ("which account does this project use?"), and the UI asks
# the first one first. These cover both shapes of connector — OAuth and pasted
# API key — because a count that quietly knows only about Google is the bug
# this endpoint exists to end.
# ---------------------------------------------------------------------------

def _sources_by_id(payload):
    return {row["connector_id"]: row for row in payload}


def test_project_data_sources_reports_bound_available_and_not_connected(
    db, cfg, owner, project
):
    # OAuth-shaped, bound to this project.
    ga4 = _store(db, owner, "ga4", "properties/1", {"refresh_token": "rt"}, account_name="Main")
    _bind(db, project, ga4, owner)
    # API-key-shaped, stored but never bound — usable, not chosen.
    _store(db, owner, "stripe", "acct_A", {"api_key": "rk_a"}, account_name="Client A")

    client = _make_client(db, owner)
    res = client.get(f"/api/user/projects/{project.id}/data-sources")
    assert res.status_code == 200
    rows = _sources_by_id(res.json())

    assert rows["ga4"]["status"] == "bound"
    assert rows["ga4"]["account_name"] == "Main"
    assert rows["stripe"]["status"] == "available"
    # The whole registry comes back, so "nothing stored" is visible too.
    assert any(r["status"] == "not_connected" for r in rows.values())


def test_data_sources_cover_oauth_and_manual_connectors(db, cfg, owner, project):
    client = _make_client(db, owner)
    rows = _sources_by_id(client.get(f"/api/user/projects/{project.id}/data-sources").json())

    kinds = {row["auth_kind"] for row in rows.values()}
    assert kinds == {"oauth", "manual"}, "both connector shapes must be inventoried"
    # A representative of each, so a registry regression is loud rather than silent.
    assert rows["ga4"]["auth_kind"] == "oauth"
    assert rows["stripe"]["auth_kind"] == "manual"


def test_project_data_sources_are_membership_gated(db, cfg, owner, project):
    outsider = User(email="pc-outsider@example.com")
    db.add(outsider)
    db.commit()
    db.refresh(outsider)

    res = _make_client(db, outsider).get(f"/api/user/projects/{project.id}/data-sources")
    # 404 rather than 403: a non-member must not learn the project exists.
    assert res.status_code == 404


def test_collaborator_sees_the_projects_data_sources(db, cfg, owner, collaborator, project):
    cred = _store(db, owner, "stripe", "acct_A", {"api_key": "rk_a"})
    _bind(db, project, cred, owner)

    rows = _sources_by_id(
        _make_client(db, collaborator)
        .get(f"/api/user/projects/{project.id}/data-sources")
        .json()
    )
    # The binding points at the OWNER's credential row; that is the point of a
    # shared project, so a collaborator sees it as bound rather than missing.
    assert rows["stripe"]["status"] == "bound"


def test_account_data_sources_answer_without_a_project(db, cfg, owner):
    _store(db, owner, "mixpanel", "proj_1", {"service_account_secret": "s"})
    _store(db, owner, "ga4", "properties/1", {"refresh_token": "rt"})

    app = FastAPI()
    app.include_router(uc_routes.router, prefix="/api/user/connectors")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: owner
    rows = _sources_by_id(TestClient(app).get("/api/user/connectors/data-sources").json())

    # No project means no bindings — stored credentials are `available`, which is
    # what the day-one checklist counts.
    assert rows["mixpanel"]["status"] == "available"
    assert rows["ga4"]["status"] == "available"
    assert rows["stripe"]["status"] == "not_connected"


def test_account_data_sources_route_is_not_shadowed_by_the_delete_path(db, cfg, owner):
    """`/data-sources` must not be read as a connector id by DELETE /{id}."""
    app = FastAPI()
    app.include_router(uc_routes.router, prefix="/api/user/connectors")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: owner
    assert TestClient(app).get("/api/user/connectors/data-sources").status_code == 200
