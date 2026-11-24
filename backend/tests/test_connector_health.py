"""A Google sign-in the provider refuses reads as Reconnect, not Connected.

The card used to be green whenever a credential row existed, so a revoked or
expired Google sign-in (or one minted by another OAuth client) stayed
"Connected" while every read through it failed, and the property picker's
listing died as a 500 the browser could only see as a network error.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError
from sqlmodel import Session

import routes.user_connectors as uc_routes
import service.auth as auth_service
import service.credentials as credentials_service
import service.google.gsc  # noqa: F401 - registers the connector
from db.session import get_session as get_session_dep
from models.auth import User
from models.connector import ConnectorCredential
from service.connector_health import is_refused_grant, record_read
from service.connector_store import upsert_credential
from service.connectors import get_connector
from service.credentials import encrypt_credentials
from tests.conftest import make_sqlite_engine

_KEY = Fernet.generate_key().decode()


class _Cfg:
    credentials_encryption_key = _KEY


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(credentials_service, "get_configs", lambda: _Cfg())
    with Session(make_sqlite_engine(drop_partial_indexes=True)) as session:
        yield session


@pytest.fixture
def alice(db):
    user = User(email="alice@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def gsc_row(db, alice):
    row = ConnectorCredential(
        user_id=alice.id, connector_type="gsc", account_id="", account_name="",
        credentials_enc=encrypt_credentials({"refresh_token": "old"}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def http(db, alice):
    app = FastAPI()
    app.include_router(uc_routes.router, prefix="/api/user/connectors")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: alice
    return TestClient(app)


def _listing_raises(monkeypatch, exc):
    _meta, adapter = get_connector("gsc")

    def boom(_auth):
        raise exc

    monkeypatch.setattr(adapter, "list_accounts", boom)


def _listing_returns(monkeypatch, entities):
    _meta, adapter = get_connector("gsc")
    monkeypatch.setattr(adapter, "list_accounts", lambda _auth: entities)


@pytest.mark.parametrize(
    ("exc", "refused"),
    [
        # Google's own shape: a message, then the token endpoint's body.
        (RefreshError("invalid_grant: Bad Request", {"error": "invalid_grant"}), True),
        (RefreshError("unauthorized_client: Unauthorized", {"error": "unauthorized_client"}), True),
        (RefreshError("invalid_grant: Token has been expired or revoked."), True),
        # The server's own client is wrong: a reconnect cannot fix that.
        (RefreshError("invalid_client: Unauthorized", {"error": "invalid_client"}), False),
        # Google asked for a retry: the sign-in itself is fine.
        (RefreshError("internal_failure", {"error": "invalid_grant"}, retryable=True), False),
        (RuntimeError("invalid_grant"), False),
    ],
)
def test_only_a_refusal_a_new_sign_in_fixes_counts(exc, refused):
    assert is_refused_grant(exc) is refused


def test_a_refused_listing_says_so_and_turns_the_card(http, db, gsc_row, monkeypatch):
    _listing_raises(monkeypatch, RefreshError("invalid_grant: Bad Request", {"error": "invalid_grant"}))

    res = http.get(f"/api/user/connectors/{gsc_row.id}/entities")

    assert res.status_code == 409
    assert res.json()["detail"] == "connector_expired"
    [listed] = http.get("/api/user/connectors").json()
    assert listed["needs_reconnect"] is True


def test_any_other_provider_failure_is_an_answer_not_a_crash(http, gsc_row, monkeypatch):
    _listing_raises(monkeypatch, Exception("socket closed"))

    res = http.get(f"/api/user/connectors/{gsc_row.id}/entities")

    assert res.status_code == 502
    [listed] = http.get("/api/user/connectors").json()
    assert listed["needs_reconnect"] is False


def test_a_listing_that_works_clears_the_mark(http, db, gsc_row, monkeypatch):
    record_read(db, gsc_row.id, refused=True)
    _listing_returns(monkeypatch, [{"account_id": "sc-domain:getcoloris.com", "account_name": "getcoloris.com"}])

    assert http.get(f"/api/user/connectors/{gsc_row.id}/entities").status_code == 200
    [listed] = http.get("/api/user/connectors").json()
    assert listed["needs_reconnect"] is False


def test_a_reconnect_clears_the_mark(db, alice, gsc_row):
    record_read(db, gsc_row.id, refused=True)

    upsert_credential(db, user_id=alice.id, connector_type="gsc", credentials={"refresh_token": "new"})
    db.commit()

    db.refresh(gsc_row)
    assert gsc_row.needs_reconnect_at is None


def test_the_agent_sees_the_same_state(db, alice, gsc_row):
    from service.connector_access import get_data_source

    record_read(db, gsc_row.id, refused=True)

    source = get_data_source(db, "gsc", user_id=alice.id)
    assert source.as_dict()["needs_reconnect"] is True


def test_an_agent_read_that_is_refused_marks_the_sign_in_it_spent(db, alice, gsc_row, monkeypatch):
    from agents.insights import fetchers

    spec = next(s for s in fetchers.fetch_specs().values() if s.connector_id == "gsc")

    def boom(*_a, **_k):
        raise RefreshError("invalid_grant: Bad Request", {"error": "invalid_grant"})

    class _Source:
        status = "bound"
        account_id = "sc-domain:getcoloris.com"

    monkeypatch.setattr(fetchers, "fetch_specs", lambda: {spec.entity_id: replace(spec, call=boom)})
    monkeypatch.setattr("service.connector_access.get_data_source", lambda *a, **k: _Source())
    monkeypatch.setattr("db.session.get_session", lambda: iter([db]))

    result = fetchers.fetch_entity(spec.entity_id, user_id=alice.id, project_id=None)

    assert result["status"] == "reauth_required"
    # fetch_entity closes the sessions it opens, so read the row afresh.
    assert db.get(ConnectorCredential, gsc_row.id).needs_reconnect_at is not None


def test_bookkeeping_never_fails_the_read(db):
    record_read(db, uuid4(), refused=True)  # no such row: nothing to do, nothing raised
