"""Shared pytest fixtures for backend agent tests.

``tests`` is a package (see tests/__init__.py) so the evaluation harness in
``tests.eval`` and the helpers here import cleanly from individual test modules.
"""

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
