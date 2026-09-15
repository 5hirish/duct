"""A user's second project.

`uq_projects_user_slug` has been in the database since f6fa9305fb03, which
backfilled every existing slug from the project name with a per-user counter.
Nothing wrote the column afterwards, so every project created since kept the
empty-string default — which the constraint allows exactly once per user and
rejects on their second project, as an IntegrityError on a plain "create
project". The tests never caught it because they build tables with
`create_all` from the models, and the model did not declare the constraint;
`alembic check` in CI is what finally said the two disagreed.

So these are two tests for one bug: the model tells the truth about the
database now, and the code fills the column the constraint is about.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from models.auth import User
from models.project import Project, slugify, unique_slug
from tests.conftest import make_sqlite_engine


@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


@pytest.fixture
def owner(db):
    user = User(email="slug-owner@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_slugify_is_the_migrations_own_rule():
    # Same output as `_slugify` in f6fa9305fb03, which produced the slugs that
    # are in production today; a different rule here would rename them.
    assert slugify("MaxAura Lab") == "maxaura-lab"
    assert slugify("  Kestrel — Growth  ") == "kestrel-growth"
    assert slugify("") == "project"
    assert slugify("!!!") == "project"


def test_second_project_with_the_same_name_gets_a_counter(db, owner):
    first = Project(user_id=owner.id, name="Growth", slug=unique_slug(db, owner.id, "Growth"))
    db.add(first)
    db.commit()

    second = Project(user_id=owner.id, name="Growth", slug=unique_slug(db, owner.id, "Growth"))
    db.add(second)
    db.commit()

    assert first.slug == "growth"
    assert second.slug == "growth-2"


def test_the_constraint_the_model_now_declares_is_real(db, owner):
    """The regression this is guarding, spelled out.

    Two projects sharing a slug must fail. Before the model declared
    `uq_projects_user_slug`, `create_all` never built it, so this passed
    silently in tests and failed in production instead.
    """
    db.add(Project(user_id=owner.id, name="One", slug=""))
    db.commit()

    db.add(Project(user_id=owner.id, name="Two", slug=""))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_slugs_are_unique_per_user_not_globally(db, owner):
    other = User(email="slug-other@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)

    db.add(Project(user_id=owner.id, name="Growth", slug=unique_slug(db, owner.id, "Growth")))
    db.commit()

    # Someone else's "growth" is not taken as far as this user is concerned.
    assert unique_slug(db, other.id, "Growth") == "growth"


def test_renaming_a_project_may_keep_its_own_slug(db, owner):
    row = Project(user_id=owner.id, name="Growth", slug=unique_slug(db, owner.id, "Growth"))
    db.add(row)
    db.commit()
    db.refresh(row)

    # `exclude` is what stops a project colliding with itself, which would
    # otherwise walk its slug to `growth-2` on every save of an unchanged name.
    assert unique_slug(db, owner.id, "Growth", exclude=row.id) == "growth"
