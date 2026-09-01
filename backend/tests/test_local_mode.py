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
import re
import stat
import sys

import pytest
from sqlmodel import Session, SQLModel, select

import local_server
from config import Configs, cors_kwargs
from utils.appdirs import default_data_dir, resolve_data_dir


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
    # Alembic owns the desktop schema too — see db/migrate.py.
    assert cfg.init_db_on_startup is False


def test_local_mode_respects_explicit_database_url(clean_env, tmp_path):
    """A developer can still run desktop mode against Postgres."""
    cfg = Configs(
        duct_local=True,
        duct_data_dir=str(tmp_path),
        database_url="postgresql://user:pw@host/db",
    )
    assert cfg.database_url == "postgresql://user:pw@host/db"


# ---------------------------------------------------------------------------
# The credentials key the desktop shell mints
#
# Desktop had none: CREDENTIALS_ENCRYPTION_KEY is a server setting and the frozen
# bundle ships no `.env`, so service/credentials.py raised on every encrypt and
# connecting a data source could finish OAuth and then fail to persist. The
# shell now keeps a Fernet key in the OS keychain and passes it under its own
# name, which is what makes it a fallback rather than an override.
# ---------------------------------------------------------------------------


def test_local_mode_adopts_the_shells_keychain_key(clean_env, tmp_path, monkeypatch):
    monkeypatch.setenv("DUCT_KEYCHAIN_CREDENTIALS_KEY", "from-the-keychain")
    cfg = Configs(duct_local=True, duct_data_dir=str(tmp_path))
    assert cfg.credentials_encryption_key == "from-the-keychain"


def test_an_explicit_credentials_key_is_not_shadowed(clean_env, tmp_path, monkeypatch):
    """A developer running the shell against backend/.env.local keeps that
    file's key — otherwise every row they had already encrypted with it would
    stop decrypting the first time they launched the desktop build."""
    monkeypatch.setenv("DUCT_KEYCHAIN_CREDENTIALS_KEY", "from-the-keychain")
    cfg = Configs(
        duct_local=True,
        duct_data_dir=str(tmp_path),
        credentials_encryption_key="from-env-local",
    )
    assert cfg.credentials_encryption_key == "from-env-local"


def test_the_keychain_key_never_reaches_a_deployment(clean_env, monkeypatch):
    """It is applied inside the local-mode block, so Railway cannot pick up a
    stray variable of that name from the environment."""
    monkeypatch.setenv("DUCT_KEYCHAIN_CREDENTIALS_KEY", "from-the-keychain")
    assert Configs().credentials_encryption_key == ""


def test_a_url_safe_base64_of_32_bytes_is_a_valid_fernet_key():
    """The contract between the two languages, which nothing else checks.

    `credentials_encryption_key` in desktop/src-tauri/src/lib.rs builds the key
    as URL_SAFE base64 (with padding) of 32 random bytes. Nothing links the Rust
    and Python halves at compile time, so pin the shape Fernet actually accepts
    — dropping the padding, or using standard rather than url-safe base64, would
    produce a key that only fails at the first encrypt on a user's machine.
    """
    import base64 as b64
    import os as _os

    from cryptography.fernet import Fernet

    minted = b64.urlsafe_b64encode(_os.urandom(32)).decode()
    assert len(minted) == 44 and minted.endswith("=")
    token = Fernet(minted.encode()).encrypt(b"connector refresh token")
    assert Fernet(minted.encode()).decrypt(token) == b"connector refresh token"


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


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
#
# These drive desktop mode through DUCT_LOCAL rather than `Configs(duct_local=True)`.
# The field carries `validation_alias=AliasChoices("DUCT_LOCAL", "DUCT_DESKTOP")`,
# so the field *name* is not accepted as an init kwarg: passing it applies the
# local-mode defaults (which read the raw input dict) but leaves `cfg.duct_local`
# False, and `cors_kwargs` branches on exactly that attribute. The env var is
# also how the sidecar really runs — `local_server.bootstrap()` sets it.

def _allows(cfg, origin: str) -> bool:
    """Mirror how CORSMiddleware decides, for whichever branch cors_kwargs picked."""
    kwargs = cors_kwargs(cfg)
    if "allow_origin_regex" in kwargs:
        return re.search(kwargs["allow_origin_regex"], origin) is not None
    return origin in kwargs["allow_origins"]


def _desktop_cfg(clean_env, tmp_path) -> Configs:
    clean_env.setenv("DUCT_LOCAL", "1")
    clean_env.setenv("DUCT_DATA_DIR", str(tmp_path))
    clean_env.setenv("APP_ENV", "desktop")
    return Configs()


@pytest.mark.parametrize(
    "origin",
    [
        "tauri://localhost",          # bundled frontend (the eventual shape)
        "https://app.getduct.ai",     # hosted app, during the transition
        "http://localhost:3003",      # `tauri dev` against the Next dev server
        "http://127.0.0.1:3003",
    ],
)
def test_desktop_mode_allows_every_origin_the_shell_can_load(clean_env, tmp_path, origin):
    cfg = _desktop_cfg(clean_env, tmp_path)
    assert cfg.duct_local is True, "guard: desktop mode did not actually engage"
    assert _allows(cfg, origin), f"{origin} must be allowed in desktop mode"


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "http://app.getduct.ai.evil.example",
        "https://app.getduct.ai.evil.example",
        "tauri://localhost.evil.example",
    ],
)
def test_desktop_mode_rejects_foreign_origins(clean_env, tmp_path, origin):
    """The regex is anchored — a lookalike host must not slip through."""
    cfg = _desktop_cfg(clean_env, tmp_path)
    assert not _allows(cfg, origin)


def test_deployed_mode_keeps_an_explicit_allowlist(clean_env):
    """Railway must not inherit the desktop regex."""
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("FRONTEND_ORIGIN", "https://app.getduct.ai")
    clean_env.setenv("SITE_ORIGIN", "https://getduct.ai")
    cfg = Configs()
    kwargs = cors_kwargs(cfg)
    assert "allow_origin_regex" not in kwargs
    assert kwargs["allow_origins"] == ["https://app.getduct.ai", "https://getduct.ai"]


def test_local_dev_mode_allows_any_loopback_port(clean_env):
    clean_env.setenv("APP_ENV", "local")
    cfg = Configs()
    assert _allows(cfg, "http://localhost:6006")
    assert not _allows(cfg, "https://evil.example")


def test_bootstrap_provides_a_jwt_secret(clean_env, tmp_path):
    """Sign-in mints a session JWT, and a frozen bundle carries no JWT_SECRET.

    Without this the callback fails as a bare 500 *after* the user has already
    approved at Google - the one failure in the flow that cannot be seen until
    the round-trip is nearly complete.
    """
    import local_server

    clean_env.delenv("JWT_SECRET", raising=False)
    local_server.bootstrap(["--data-dir", str(tmp_path), "--port", "1"])

    secret = os.environ["JWT_SECRET"]
    assert len(secret) >= 32, "Configs rejects a JWT_SECRET shorter than 32 chars"

    mode = (tmp_path / local_server._JWT_SECRET_FILE).stat().st_mode
    assert mode & 0o077 == 0, "the signing key must not be group/other readable"


def test_jwt_secret_survives_a_restart(clean_env, tmp_path):
    """A per-boot key would sign every user out on every relaunch."""
    import local_server

    clean_env.delenv("JWT_SECRET", raising=False)
    local_server.bootstrap(["--data-dir", str(tmp_path), "--port", "1"])
    first = os.environ["JWT_SECRET"]

    clean_env.delenv("JWT_SECRET", raising=False)
    local_server.bootstrap(["--data-dir", str(tmp_path), "--port", "1"])
    assert os.environ["JWT_SECRET"] == first


# --- Which environment a run embodies -------------------------------------
#
# Duct is configured entirely through the environment: a user picks their own
# database and API URL, and the desktop sidecar is expected to embody whichever
# env it was started with rather than a hardcoded default. DUCT_ENV_FILE is the
# knob that selects one, so these pin its resolution rules.


def test_env_file_defaults_to_the_developer_pair(clean_env):
    from config import _settings_env_files

    assert [p.name for p in _settings_env_files()] == [".env", ".env.local"]


def test_env_file_override_resolves_against_the_backend_dir(clean_env):
    """A bare name has to work from any cwd — and from a frozen bundle, whose
    own directory holds no env files."""
    from config import _BACKEND_DIR, _settings_env_files

    clean_env.setenv("DUCT_ENV_FILE", ".env.prod")

    assert _settings_env_files() == (_BACKEND_DIR / ".env.prod",)


def test_env_file_override_accepts_absolute_paths_and_lists(clean_env, tmp_path):
    from config import _settings_env_files

    first, second = tmp_path / "base.env", tmp_path / "over.env"
    clean_env.setenv("DUCT_ENV_FILE", f"{first}{os.pathsep}{second}")

    assert _settings_env_files() == (first, second)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u:secret@db.example.com:5432/duct", "postgresql db.example.com:5432/duct"),
        ("sqlite:////data/duct.db", "sqlite //data/duct.db"),
        ("", "(unset)"),
    ],
)
def test_describe_database_never_leaks_the_password(url, expected):
    """This string is printed at startup and pasted into bug reports."""
    from config import describe_database

    described = describe_database(url)
    assert described == expected
    assert "secret" not in described
