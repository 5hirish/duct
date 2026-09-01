"""Shared pytest fixtures for backend agent tests.

``tests`` is a package (see tests/__init__.py) so the evaluation harness in
``tests.eval`` and the helpers here import cleanly from individual test modules.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from agents.audit.schema import AuditBusinessContext


def make_sqlite_engine(*, drop_partial_indexes: bool = False):
    """An in-memory SQLite engine with every registered SQLModel table created.

    Eleven test modules were each hand-rolling this same four-line incantation.
    The two non-obvious parts are worth stating once:

    ``StaticPool`` + ``check_same_thread=False`` share ONE connection across
    threads. ``TestClient`` runs sync handlers on a worker thread, and without
    this each thread would open its own empty ``:memory:`` database.

    ``drop_partial_indexes`` handles the Postgres-only partial indexes. SQLAlchemy
    drops the ``postgresql_where`` clause on other dialects, which turns "one
    owner per project" and "one pending invite per address" into *unconditional*
    UNIQUE constraints that reject legitimate rows. Dropping them lets these
    tests exercise the application logic; Postgres keeps them as the real
    backstop, and the migration is what enforces them in production.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    if drop_partial_indexes:
        with engine.begin() as conn:
            for index in (
                "uq_project_members_single_owner",
                "uq_project_invitations_pending_email",
            ):
                conn.exec_driver_sql(f"DROP INDEX IF EXISTS {index}")
    return engine


# Everything desktop/local mode reads or writes. Snapshotted whole by
# `clean_env`, so any of it a test writes is undone afterwards.
_LOCAL_MODE_ENV_VARS = (
    "DUCT_LOCAL", "DUCT_DESKTOP", "DUCT_DATA_DIR", "DUCT_API_KEY", "DUCT_ENV_FILE",
    "API_PUBLIC_URL", "FRONTEND_ORIGIN", "APP_ENV", "SENTRY_DSN",
    "DATABASE_URL", "UPLOADS_DIR", "INIT_DB_ON_STARTUP",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Isolate the env vars desktop/local mode reads and writes.

    Clearing the environment is not enough: Configs also reads backend/.env and
    .env.local, deliberately, so integration tests can share the running
    server's keys (see config._settings_env_files). A developer with a real
    DATABASE_URL there would otherwise see these tests try to reach Railway —
    and the failure message would print the credential.

    The restore is done by hand rather than left to monkeypatch, because
    `delenv(..., raising=False)` records *nothing* for a variable that was
    already absent — so anything the code under test then writes straight to
    `os.environ` survives the test. `local_server.bootstrap()` sets DUCT_LOCAL
    exactly that way, and a stray `DUCT_LOCAL=1` silently flips every
    desktop-shaped branch on for the rest of the session.
    """
    from config import Configs, get_configs

    saved = {var: os.environ.get(var) for var in _LOCAL_MODE_ENV_VARS}
    for var in _LOCAL_MODE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setitem(Configs.model_config, "env_file", None)

    yield monkeypatch

    for var, value in saved.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value
    # Configs is lru_cached: a config built from the environment above would
    # outlive this test however carefully the environment itself is restored.
    get_configs.cache_clear()


@pytest.fixture
def acme_business_context():
    return AuditBusinessContext(
        business_name="Acme CRM",
        business_goals="Improve organic search visibility and drive signups.",
    )


@pytest.fixture
def maxaura_business_context():
    return AuditBusinessContext(
        business_name="MaxAura",
        business_description="AI-powered grooming and self-improvement tools for men",
        business_goals="Rank for looksmaxxing, grooming, and self-improvement keywords",
        target_keywords=["looksmaxxing", "grooming tips for men", "face care routine", "jawline exercises"],
        competitors=["rmrs.com", "artofmanliness.com", "tiege.com"],
        audience_segment="men aged 18–35 interested in self-improvement and aesthetics",
        industry="health & beauty / men's grooming",
    )


@pytest.fixture
def duct_business_context():
    return AuditBusinessContext(
        business_name="Duct",
        business_description="AI-powered SEO audit and organic growth intelligence for marketers",
        business_goals="Rank for SEO audit, AIO, and organic growth keywords",
        target_keywords=["SEO audit tool", "AI SEO", "organic growth platform"],
        competitors=["semrush.com", "ahrefs.com", "searchatlas.com"],
        industry="SaaS / marketing technology",
    )
