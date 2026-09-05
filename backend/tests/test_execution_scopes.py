"""Executor permission gating — a change nobody can apply must not be offered.

Google's consent screen is per-scope, so a project can hold a working GA4
connection and still lack ``analytics.edit``. Before this gate the first sign of
that was a 403 at apply time — after a human had approved the change, which is
the worst possible moment to discover it.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session

import service.credentials as credentials_service
import service.execution.ga4_exec  # noqa: F401 — registration is an import side effect
import service.execution.google_ads_exec  # noqa: F401
import service.execution.gtm_exec  # noqa: F401
import service.execution.mixpanel_exec  # noqa: F401
from config import Configs
from models.auth import User
from models.connector import ConnectorCredential, ProjectConnector
from models.project import Project
from service.connector_access import granted_scopes_for
from service.execution.registry import EXECUTOR_REGISTRY, missing_scopes_for
from tests.conftest import make_sqlite_engine

GA4_EDIT = "https://www.googleapis.com/auth/analytics.edit"
GA4_READ = "https://www.googleapis.com/auth/analytics.readonly"
GTM_PUBLISH = "https://www.googleapis.com/auth/tagmanager.publish"
GTM_EDIT = "https://www.googleapis.com/auth/tagmanager.edit.containers"

FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
def db_session():
    engine = make_sqlite_engine()
    with Session(engine) as session:
        yield session


@pytest.fixture
def cfg(monkeypatch):
    config = Configs(credentials_encryption_key=FERNET_KEY)
    monkeypatch.setattr(credentials_service, "get_configs", lambda: config)
    return config


@pytest.fixture
def user(db_session):
    row = User(email="scope-test@example.com")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _store(db_session, user, connector_type, granted, account_id=""):
    row = ConnectorCredential(
        user_id=user.id,
        connector_type=connector_type,
        account_id=account_id,
        credentials_enc=credentials_service.encrypt_credentials({"refresh_token": "rt"}),
        granted_scopes=granted,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# --- the rule -------------------------------------------------------------


def test_a_recorded_grant_that_lacks_the_scope_blocks():
    spec = EXECUTOR_REGISTRY["ga4.create_key_event"]
    assert missing_scopes_for(spec, [GA4_READ]) == [GA4_EDIT]


def test_a_recorded_grant_that_holds_the_scope_allows():
    spec = EXECUTOR_REGISTRY["ga4.create_key_event"]
    assert missing_scopes_for(spec, [GA4_READ, GA4_EDIT]) == []


def test_an_unrecorded_grant_is_unknown_and_never_blocks():
    """Empty means "we did not record it", not "nothing was granted".

    Every connection made before grants were recorded has an empty string here.
    Blocking those would break working setups over a fact we simply do not have;
    letting them through fails at the provider exactly as it did before, which
    is the strictly better wrong answer.
    """
    spec = EXECUTOR_REGISTRY["ga4.create_key_event"]
    assert missing_scopes_for(spec, []) == []


def test_an_executor_needing_nothing_extra_never_blocks():
    spec = EXECUTOR_REGISTRY["mixpanel.create_annotation"]
    assert spec.required_scopes == frozenset()
    assert missing_scopes_for(spec, [GA4_READ]) == []


# --- the declarations -----------------------------------------------------


@pytest.mark.parametrize(
    "connector, scope",
    [("ga4", GA4_EDIT), ("google_ads", "https://www.googleapis.com/auth/adwords")],
)
def test_every_write_executor_declares_its_scope(connector, scope):
    """A new executor that forgets this silently loses the gate, and the loss is
    invisible until someone with a partial grant approves one of its changes."""
    specs = [s for s in EXECUTOR_REGISTRY.values() if s.connector_type == connector]
    assert specs, f"no executors registered for {connector}"
    for spec in specs:
        assert scope in spec.required_scopes, f"{spec.op_type} declares no scope"


def test_gtm_separates_editing_from_publishing():
    """GTM's consent screen splits them, so the gate has to as well: someone who
    grants edit but not publish can still have Duct stage a change for them."""
    assert EXECUTOR_REGISTRY["gtm.upsert_tag"].required_scopes == frozenset({GTM_EDIT})
    assert EXECUTOR_REGISTRY["gtm.publish_version"].required_scopes == frozenset({GTM_PUBLISH})

    staged_only = [GTM_EDIT]
    assert missing_scopes_for(EXECUTOR_REGISTRY["gtm.upsert_tag"], staged_only) == []
    assert missing_scopes_for(EXECUTOR_REGISTRY["gtm.publish_version"], staged_only) == [
        GTM_PUBLISH
    ]


# --- reading the grant off the right row ----------------------------------


def test_the_grant_is_read_from_the_same_row_the_secret_comes_from(db_session, cfg, user):
    """The project's bound account wins, exactly as it does for credentials.

    Answering a permission question about a different account than the call will
    use is the bug this whole line of work exists to prevent.
    """
    project = Project(user_id=user.id, name="Scope Test")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    _store(db_session, user, "ga4", GA4_READ, account_id="")
    bound_row = _store(db_session, user, "ga4", f"{GA4_READ} {GA4_EDIT}", account_id="properties/9")
    db_session.add(
        ProjectConnector(
            project_id=project.id,
            connector_type="ga4",
            connector_credential_id=bound_row.id,
        )
    )
    db_session.commit()

    assert granted_scopes_for(
        db_session, user_id=user.id, connector_type="ga4", project_id=project.id
    ) == [GA4_READ, GA4_EDIT]

    # Without the project, the caller's own account-agnostic row answers.
    assert granted_scopes_for(db_session, user_id=user.id, connector_type="ga4") == [GA4_READ]


def test_no_row_at_all_reads_as_unknown(db_session, cfg, user):
    assert granted_scopes_for(db_session, user_id=user.id, connector_type="gtm") == []
