"""Unit tests for execution credential resolution (override → stored → env)."""

from __future__ import annotations


import pytest

from tests.conftest import make_sqlite_engine
from cryptography.fernet import Fernet
from sqlmodel import Session

from config import Configs
from models.auth import User
from models.connector import ConnectorCredential
import service.credentials as credentials_service
import service.execution.creds as creds_module
from service.execution.creds import resolve_execution_creds

FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
def db_session():
    engine = make_sqlite_engine()
    with Session(engine) as session:
        yield session


@pytest.fixture
def cfg(monkeypatch):
    config = Configs(
        credentials_encryption_key=FERNET_KEY,
        google_ads_developer_token="env-dev-token",
        google_ads_login_customer_id="env-mcc",
        google_oauth_client_id="env-client-id",
        google_oauth_client_secret="env-client-secret",
    )
    monkeypatch.setattr(creds_module, "get_configs", lambda: config)
    monkeypatch.setattr(credentials_service, "get_configs", lambda: config)
    return config


@pytest.fixture
def user(db_session):
    row = User(email="creds-test@example.com")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _store(db_session, user, connector_type, account_id, data):
    row = ConnectorCredential(
        user_id=user.id,
        connector_type=connector_type,
        account_id=account_id,
        credentials_enc=credentials_service.encrypt_credentials(data),
    )
    db_session.add(row)
    db_session.commit()


def test_env_fallback_when_nothing_stored(db_session, cfg, user):
    creds = resolve_execution_creds(db_session, user.id, "google_ads")
    assert creds["refresh_token"] == ""
    assert creds["developer_token"] == "env-dev-token"
    assert creds["login_customer_id"] == "env-mcc"
    assert creds["client_id"] == "env-client-id"
    assert creds["client_secret"] == "env-client-secret"


def test_stored_credentials_used_when_override_empty(db_session, cfg, user):
    _store(db_session, user, "google_ads", "", {"refresh_token": "stored-rt", "developer_token": "stored-dev"})
    creds = resolve_execution_creds(db_session, user.id, "google_ads")
    assert creds["refresh_token"] == "stored-rt"
    assert creds["developer_token"] == "stored-dev"
    # Unset stored fields still fall through to env.
    assert creds["login_customer_id"] == "env-mcc"


def test_override_wins_over_stored(db_session, cfg, user):
    _store(db_session, user, "google_ads", "", {"refresh_token": "stored-rt"})
    creds = resolve_execution_creds(
        db_session, user.id, "google_ads", override={"refresh_token": "byo-rt"}
    )
    assert creds["refresh_token"] == "byo-rt"


def test_account_specific_row_preferred(db_session, cfg, user):
    _store(db_session, user, "google_ads", "", {"refresh_token": "generic-rt"})
    _store(db_session, user, "google_ads", "1112223333", {"refresh_token": "acct-rt"})
    creds = resolve_execution_creds(db_session, user.id, "google_ads", account_id="1112223333")
    assert creds["refresh_token"] == "acct-rt"
    # Unknown account falls back to the account-agnostic row.
    creds = resolve_execution_creds(db_session, user.id, "google_ads", account_id="0000000000")
    assert creds["refresh_token"] == "generic-rt"


def test_connector_type_scoping(db_session, cfg, user):
    _store(db_session, user, "ga4", "", {"refresh_token": "ga4-rt"})
    creds = resolve_execution_creds(db_session, user.id, "google_ads")
    assert creds["refresh_token"] == ""


def test_missing_encryption_key_degrades_to_env(db_session, cfg, user, monkeypatch):
    _store(db_session, user, "google_ads", "", {"refresh_token": "stored-rt"})
    broken = Configs(
        credentials_encryption_key="",
        google_ads_developer_token="env-dev-token",
        google_oauth_client_id="env-client-id",
        google_oauth_client_secret="env-client-secret",
    )
    monkeypatch.setattr(creds_module, "get_configs", lambda: broken)
    monkeypatch.setattr(credentials_service, "get_configs", lambda: broken)
    creds = resolve_execution_creds(db_session, user.id, "google_ads")
    assert creds["refresh_token"] == ""  # stored row unreadable → skipped, no raise
    assert creds["developer_token"] == "env-dev-token"
