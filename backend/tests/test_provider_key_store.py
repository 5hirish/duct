"""Saved bring-your-own provider keys — the half a header cannot cover.

An ``X-Provider-*`` header needs a request to ride on, so header-only BYOK
leaves every browserless run (a scheduled brief, memory consolidation, a
content session's image tools) with nothing but Duct's env key. These pin the
store that closes that, and the two properties that make it worth having:
the secret round-trips, and it is never handed back out.

No network. SQLite in memory, a throwaway Fernet key.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, select

import service.credentials as credentials_service
from agents.models import Provider
from config import Configs
from models.auth import User
from models.connector import ConnectorCredential
from service.provider_keys import (
    CONNECTOR_TYPE,
    delete_provider_key,
    has_stored_provider_keys,
    save_provider_key,
    stored_provider_keys,
)
from tests.conftest import make_sqlite_engine

FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
def db():
    engine = make_sqlite_engine(drop_partial_indexes=True)
    with Session(engine) as session:
        yield session


@pytest.fixture
def cfg(monkeypatch):
    config = Configs(credentials_encryption_key=FERNET_KEY)
    monkeypatch.setattr(credentials_service, "get_configs", lambda: config)
    return config


@pytest.fixture
def user(db):
    row = User(email="byok@example.com")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_a_saved_key_round_trips(db, cfg, user):
    save_provider_key(db, user.id, Provider.ANTHROPIC, "sk-ant-mine")
    assert stored_provider_keys(db, user.id) == {Provider.ANTHROPIC: "sk-ant-mine"}


def test_the_key_is_not_stored_in_the_clear(db, cfg, user):
    """The row is what an operator with database access sees. It must not be
    the secret."""
    save_provider_key(db, user.id, Provider.OPENAI, "sk-openai-mine")
    row = db.exec(
        select(ConnectorCredential).where(ConnectorCredential.connector_type == CONNECTOR_TYPE)
    ).one()
    assert "sk-openai-mine" not in row.credentials_enc
    assert row.account_id == Provider.OPENAI.value


def test_saving_twice_replaces_rather_than_accumulates(db, cfg, user):
    """Rotating a key must leave the old secret nowhere — a second row would be
    a revoked key still on disk."""
    save_provider_key(db, user.id, Provider.ANTHROPIC, "sk-ant-old")
    save_provider_key(db, user.id, Provider.ANTHROPIC, "sk-ant-new")
    rows = db.exec(
        select(ConnectorCredential).where(ConnectorCredential.connector_type == CONNECTOR_TYPE)
    ).all()
    assert len(rows) == 1
    assert stored_provider_keys(db, user.id) == {Provider.ANTHROPIC: "sk-ant-new"}


def test_a_blank_key_is_a_delete(db, cfg, user):
    """What the settings page sends when the field is cleared. Leaving the old
    secret behind would be the one behaviour nobody expects."""
    save_provider_key(db, user.id, Provider.ANTHROPIC, "sk-ant-mine")
    save_provider_key(db, user.id, Provider.ANTHROPIC, "   ")
    assert stored_provider_keys(db, user.id) == {}


def test_delete_is_idempotent(db, cfg, user):
    delete_provider_key(db, user.id, Provider.OPENROUTER)  # never saved
    save_provider_key(db, user.id, Provider.OPENROUTER, "sk-or-v1-mine")
    delete_provider_key(db, user.id, Provider.OPENROUTER)
    delete_provider_key(db, user.id, Provider.OPENROUTER)
    assert stored_provider_keys(db, user.id) == {}


def test_presence_is_readable_without_decrypting(db, cfg, user):
    """The status endpoint answers "is one saved?" and must not need the key to
    do it — that is the difference between reporting a fact and handling a
    secret."""
    save_provider_key(db, user.id, Provider.GOOGLE_GENAI, "AIza-mine")
    assert has_stored_provider_keys(db, user.id) == {Provider.GOOGLE_GENAI}


def test_keys_do_not_leak_between_users(db, cfg, user):
    other = User(email="someone-else@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    save_provider_key(db, user.id, Provider.ANTHROPIC, "sk-ant-mine")
    assert stored_provider_keys(db, other.id) == {}
    assert has_stored_provider_keys(db, other.id) == set()


def test_an_anonymous_caller_has_no_saved_keys(db, cfg):
    """Signed-out reads happen — the status endpoint takes an optional user."""
    assert stored_provider_keys(db, None) == {}
    assert has_stored_provider_keys(db, None) == set()


def test_an_unreadable_key_degrades_instead_of_raising(db, cfg, user, monkeypatch):
    """A rotated CREDENTIALS_ENCRYPTION_KEY must cost a run its BYO key, not
    turn every run into a 500. Same never-raise contract the connector
    credential reader keeps."""
    save_provider_key(db, user.id, Provider.ANTHROPIC, "sk-ant-mine")
    monkeypatch.setattr(
        credentials_service,
        "get_configs",
        lambda: Configs(credentials_encryption_key=Fernet.generate_key().decode()),
    )
    assert stored_provider_keys(db, user.id) == {}
    # Presence still reads, because it never touches the ciphertext.
    assert has_stored_provider_keys(db, user.id) == {Provider.ANTHROPIC}
