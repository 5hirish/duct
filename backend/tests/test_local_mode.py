"""Desktop (local sidecar) mode — data dir, handshake, SQLite persistence.

Covers the contract the Tauri shell depends on: `local_server.bootstrap()`
prepares the environment and returns a handshake, and `Configs` in local mode
points persistence at the per-user data dir instead of Railway.

Every test drives an explicit `--data-dir` into tmp_path so nothing touches the
developer's real ~/Library or ~/.local/share.
"""

from __future__ import annotations

import json
import os
import stat
import sys

import pytest
from sqlmodel import Session, SQLModel, select

import local_server
from config import Configs
from utils.appdirs import default_data_dir, resolve_data_dir


@pytest.fixture
def clean_env(monkeypatch):
    """Isolate the env vars local mode reads and writes."""
    for var in (
        "DUCT_LOCAL", "DUCT_DESKTOP", "DUCT_DATA_DIR", "DUCT_API_KEY",
        "API_PUBLIC_URL", "FRONTEND_ORIGIN", "APP_ENV", "SENTRY_DSN",
        "DATABASE_URL", "UPLOADS_DIR", "INIT_DB_ON_STARTUP",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------

def test_default_data_dir_is_os_conventional():
    path = str(default_data_dir())
    if sys.platform == "darwin":
        assert path.endswith("Library/Application Support/ai.getduct.desktop")
    elif sys.platform == "win32":
        assert path.endswith("Duct")
    else:
        assert path.endswith("duct")


def test_explicit_override_wins_over_env(clean_env, tmp_path):
    clean_env.setenv("DUCT_DATA_DIR", str(tmp_path / "from-env"))
    assert resolve_data_dir(str(tmp_path / "explicit")) == tmp_path / "explicit"


def test_env_used_when_no_override(clean_env, tmp_path):
    clean_env.setenv("DUCT_DATA_DIR", str(tmp_path / "from-env"))
    assert resolve_data_dir() == tmp_path / "from-env"


# ---------------------------------------------------------------------------
# Handshake
# ---------------------------------------------------------------------------

def test_bootstrap_returns_handshake_and_sets_env(clean_env, tmp_path):
    handshake = local_server.bootstrap(["--data-dir", str(tmp_path)])

    assert handshake["duct_sidecar"] == 1
    assert handshake["port"] > 0
    assert handshake["url"] == f"http://127.0.0.1:{handshake['port']}"
    assert handshake["data_dir"] == str(tmp_path)
    assert handshake["api_key"]

    assert os.environ["DUCT_LOCAL"] == "1"
    assert os.environ["DUCT_DATA_DIR"] == str(tmp_path)
    assert os.environ["DUCT_API_KEY"] == handshake["api_key"]
    assert os.environ["API_PUBLIC_URL"] == handshake["url"]


def test_handshake_is_one_json_line(clean_env, tmp_path):
    """The shell reads exactly one line and json-decodes it."""
    handshake = local_server.bootstrap(["--data-dir", str(tmp_path)])
    line = json.dumps(handshake)
    assert "\n" not in line
    assert json.loads(line)["duct_sidecar"] == 1


def test_bootstrap_binds_loopback_only(clean_env, tmp_path):
    handshake = local_server.bootstrap(["--data-dir", str(tmp_path)])
    assert handshake["url"].startswith("http://127.0.0.1:")


def test_explicit_port_is_honoured(clean_env, tmp_path):
    handshake = local_server.bootstrap(["--data-dir", str(tmp_path), "--port", "51999"])
    assert handshake["port"] == 51999


def test_ports_differ_across_instances(clean_env, tmp_path):
    """Two windows must not collide — port 0 asks the OS each time."""
    first = local_server.bootstrap(["--data-dir", str(tmp_path)])["port"]
    second = local_server.bootstrap(["--data-dir", str(tmp_path)])["port"]
    assert first != second


def test_bootstrap_does_not_override_explicit_app_env(clean_env, tmp_path):
    clean_env.setenv("APP_ENV", "local")
    local_server.bootstrap(["--data-dir", str(tmp_path)])
    assert os.environ["APP_ENV"] == "local"


# ---------------------------------------------------------------------------
# Local API key
# ---------------------------------------------------------------------------

def test_api_key_persists_across_restarts(clean_env, tmp_path):
    first = local_server.bootstrap(["--data-dir", str(tmp_path)])["api_key"]
    second = local_server.bootstrap(["--data-dir", str(tmp_path)])["api_key"]
    assert first == second


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_api_key_file_is_owner_only(clean_env, tmp_path):
    local_server.bootstrap(["--data-dir", str(tmp_path)])
    mode = (tmp_path / local_server._API_KEY_FILE).stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


# ---------------------------------------------------------------------------
# Config derivation
# ---------------------------------------------------------------------------

def test_local_mode_derives_sqlite_and_uploads(clean_env, tmp_path):
    cfg = Configs(duct_local=True, duct_data_dir=str(tmp_path))

    assert cfg.database_url == f"sqlite:///{tmp_path / 'duct.db'}"
    assert cfg.uploads_dir == str(tmp_path / "uploads")
    # No Alembic step on a user's laptop.
    assert cfg.init_db_on_startup is True


def test_local_mode_respects_explicit_database_url(clean_env, tmp_path):
    """A developer can still run desktop mode against Postgres."""
    cfg = Configs(
        duct_local=True,
        duct_data_dir=str(tmp_path),
        database_url="postgresql://user:pw@host/db",
    )
    assert cfg.database_url == "postgresql://user:pw@host/db"


def test_server_mode_is_untouched(clean_env):
    """Railway config must not acquire desktop defaults."""
    cfg = Configs()
    assert cfg.duct_local is False
    assert cfg.database_url == ""
    assert cfg.init_db_on_startup is False


def test_duct_local_accepts_env_string(clean_env, tmp_path):
    """DUCT_LOCAL arrives from the env as "1", not a bool."""
    clean_env.setenv("DUCT_LOCAL", "1")
    clean_env.setenv("DUCT_DATA_DIR", str(tmp_path))
    cfg = Configs()
    assert cfg.duct_local is True
    assert cfg.database_url.startswith("sqlite:///")


# ---------------------------------------------------------------------------
# SQLite engine
# ---------------------------------------------------------------------------

def test_sqlite_engine_creates_schema_and_round_trips(clean_env, tmp_path, monkeypatch):
    """The real model metadata must create cleanly on SQLite, not just Postgres."""
    import db.session as db_session
    import models  # noqa: F401 — registers SQLModel metadata

    cfg = Configs(duct_local=True, duct_data_dir=str(tmp_path))
    monkeypatch.setattr(db_session, "get_configs", lambda: cfg)
    db_session.get_engine.cache_clear()

    engine = db_session.get_engine()
    assert engine is not None
    SQLModel.metadata.create_all(engine)
    assert (tmp_path / "duct.db").exists()

    from models.auth import User

    with Session(engine) as session:
        session.add(User(email="local@example.com"))
        session.commit()
    with Session(engine) as session:
        found = session.exec(select(User).where(User.email == "local@example.com")).first()
        assert found is not None

    db_session.get_engine.cache_clear()


def test_sqlite_engine_enables_wal(clean_env, tmp_path, monkeypatch):
    """WAL lets an agent write while a request reads — without it, streaming
    sessions hit 'database is locked'."""
    import db.session as db_session

    cfg = Configs(duct_local=True, duct_data_dir=str(tmp_path))
    monkeypatch.setattr(db_session, "get_configs", lambda: cfg)
    db_session.get_engine.cache_clear()

    engine = db_session.get_engine()
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert str(mode).lower() == "wal"

    db_session.get_engine.cache_clear()
