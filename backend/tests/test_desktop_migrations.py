"""The desktop sidecar's schema path — Alembic, across the three install states.

The bug these guard against is silent: `create_all` creates missing *tables* and
nothing else, so an install that upgraded from an earlier build kept its old
columns and failed at query time (`no such column: projects.memory_paused`).
A fresh install was always fine, which is why it survived testing.
"""

from __future__ import annotations

from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy import inspect

from db.migrate import alembic_config, ensure_schema


def _sqlite_url(tmp_path):
    return f"sqlite:///{tmp_path / 'duct.db'}"


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _stamped_revision(engine):
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


def _local_engine(clean_env, tmp_path):
    """A configured desktop-mode engine, with the config caches cleared."""
    import config as config_module
    from db import session as session_module

    clean_env.setenv("DUCT_LOCAL", "1")
    clean_env.setenv("DUCT_DATA_DIR", str(tmp_path))
    config_module.get_configs.cache_clear()
    session_module.get_engine.cache_clear()
    return session_module.get_engine()


def test_fresh_install_lands_at_head(clean_env, tmp_path):
    """An empty data dir gets the current schema, stamped as current."""
    engine = _local_engine(clean_env, tmp_path)
    ensure_schema()

    heads = alembic_config(_sqlite_url(tmp_path))
    from alembic.script import ScriptDirectory

    expected = ScriptDirectory.from_config(heads).get_current_head()
    assert _stamped_revision(engine) == expected
    # The column whose absence was the actual failure mode.
    assert "memory_paused" in _columns(engine, "projects")
    assert "memory_paused" in _columns(engine, "users")


def test_legacy_create_all_install_is_adopted_and_upgraded(clean_env, tmp_path):
    """A pre-Alembic install (tables, no alembic_version) migrates forward.

    This is the regression: before `db/migrate.py`, such an install kept its old
    schema forever because `create_all` saw the tables and did nothing.

    The legacy state is built with `create_all` and then walked *back* to the
    baseline, rather than by replaying migrations from `base` — the pre-baseline
    revisions declare raw `postgresql.JSONB` and cannot run on SQLite at all
    (see `db/migrate.py`). That is faithful to what shipped: those installs were
    created by `create_all`, never by Alembic.

    The walk-back below is a fixture, not a fact: every post-baseline migration
    adds one line to it. A new `add_column` that is not dropped here fails with
    "duplicate column", which is the test doing its job — `create_all` built the
    column from today's models, so the legacy state has to lose it again.
    """
    import models  # noqa: F401 — registers the tables create_all builds

    from db.session import init_db

    engine = _local_engine(clean_env, tmp_path)
    init_db()
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE project_memories"))
        conn.execute(sa.text("ALTER TABLE projects DROP COLUMN memory_paused"))
        conn.execute(sa.text("ALTER TABLE users DROP COLUMN memory_paused"))
        conn.execute(sa.text("ALTER TABLE artifacts DROP COLUMN pinned"))
        conn.execute(sa.text("ALTER TABLE agent_conversations DROP COLUMN pinned"))
        conn.execute(sa.text("ALTER TABLE connector_credentials DROP COLUMN granted_scopes"))
        conn.execute(sa.text("ALTER TABLE project_connectors DROP COLUMN entity_id"))
        conn.execute(sa.text("ALTER TABLE project_connectors DROP COLUMN entity_name"))
        conn.execute(sa.text("ALTER TABLE connector_credentials DROP COLUMN residency"))

    assert "alembic_version" not in set(inspect(engine).get_table_names())
    assert "memory_paused" not in _columns(engine, "projects")

    ensure_schema()

    # Every post-baseline migration ran: the new table and the new columns.
    assert "project_memories" in set(inspect(engine).get_table_names())
    assert "memory_paused" in _columns(engine, "projects")
    assert "memory_paused" in _columns(engine, "users")
    assert "pinned" in _columns(engine, "artifacts")
    assert "pinned" in _columns(engine, "agent_conversations")
    assert _stamped_revision(engine) is not None


def test_repeated_startup_is_idempotent(clean_env, tmp_path):
    """Every launch runs this; the second must be a no-op, not an error."""
    engine = _local_engine(clean_env, tmp_path)
    ensure_schema()
    first = _stamped_revision(engine)
    ensure_schema()
    assert _stamped_revision(engine) == first


def test_server_mode_is_never_migrated(clean_env, tmp_path):
    """Railway runs migrations as a deploy step; startup must not touch them."""
    import config as config_module
    from db import session as session_module

    clean_env.setenv("DATABASE_URL", _sqlite_url(tmp_path))
    config_module.get_configs.cache_clear()
    session_module.get_engine.cache_clear()

    ensure_schema()  # no-op: duct_local is false

    engine = session_module.get_engine()
    assert "alembic_version" not in set(inspect(engine).get_table_names())


def test_a_remote_database_is_not_this_installs_to_migrate(monkeypatch):
    """The sidecar uses whatever DATABASE_URL points at, but only migrates what
    it owns. A server database is migrated by its deployment — a desktop build
    reshaping it (possibly *backwards*, if the build is behind) is never right.
    """
    from db import migrate

    monkeypatch.setattr("config.get_configs", lambda: SimpleNamespace(duct_local=True))
    monkeypatch.setattr(
        "db.session.get_engine",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )

    def _explode(*args, **kwargs):
        raise AssertionError("migrations must not run against a database we do not own")

    monkeypatch.setattr(migrate.command, "upgrade", _explode)
    monkeypatch.setattr(migrate.command, "stamp", _explode)
    # Reaching for the table list would already mean connecting to someone
    # else's database, so that is a failure too.
    monkeypatch.setattr(
        migrate, "inspect", lambda _: (_ for _ in ()).throw(AssertionError("connected"))
    )

    migrate.ensure_schema()  # returns quietly; any migration attempt raises


def test_a_local_sqlite_database_is_ours_to_migrate():
    from db.migrate import _owns_database

    assert _owns_database(SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))) is True
    assert _owns_database(SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))) is False
