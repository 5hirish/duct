"""Refreshing a saved insight reads the caller's stored connections.

It used to take Google refresh tokens in the body, from whichever tab sent it,
so a brief refreshed only where the connect had happened (issue #456).
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import routes.reports as reports
import service.auth as auth_service
import service.credentials as credentials_service
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.connector import ConnectorCredential
from service.credentials import encrypt_credentials
from tests.conftest import make_sqlite_engine


@pytest.fixture
def db(monkeypatch):
    config = Configs(credentials_encryption_key=Fernet.generate_key().decode())
    monkeypatch.setattr(credentials_service, "get_configs", lambda: config)
    with Session(make_sqlite_engine()) as session:
        yield session


@pytest.fixture
def alice(db):
    user = User(email="alice@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def fetched(monkeypatch):
    """What each connector would have been fetched with, instead of fetching."""
    calls: dict[str, dict] = {}

    async def fake_fetch(*, connector_id, credentials=None, **kwargs):
        calls[connector_id] = {"credentials": credentials, **kwargs}
        return {"rows": []}

    monkeypatch.setattr(reports, "fetch_connector_payload", fake_fetch)
    monkeypatch.setattr(reports, "build_connector_brief", lambda **k: {"ok": True})
    return calls


def _client(db, user):
    app = FastAPI()
    app.include_router(reports.router, prefix="/api/insights")
    app.dependency_overrides[get_session_dep] = lambda: db
    if user is not None:
        app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app)


def test_a_refresh_reads_the_stored_token_for_the_routines_account(db, alice, fetched):
    for account_id, token in (("", "generic"), ("properties/1", "for-this-property")):
        db.add(ConnectorCredential(
            user_id=alice.id, connector_type="ga4", account_id=account_id, account_name="",
            credentials_enc=encrypt_credentials({"refresh_token": token}),
        ))
    db.commit()

    res = _client(db, alice).post("/api/insights/refresh", json={
        "connections": ["ga4"],
        "targets": {"ga4": {"property_id": "properties/1"}},
        # A client still sending one is ignored, not obeyed.
        "ga4_refresh_token": "from-the-browser",
    })

    assert res.status_code == 200, res.text
    assert fetched["ga4"]["credentials"]["refresh_token"] == "for-this-property"


def test_a_refresh_needs_a_signed_in_user(db, fetched):
    res = _client(db, None).post("/api/insights/refresh", json={"connections": ["ga4"]})
    assert res.status_code == 401
    assert fetched == {}
