"""A guest is a real user, and sign-in is a link or a merge.

Onboarding runs an audit before anyone signs in. Everything that audit writes
needs an owner, so the guest *is* one — a ``users`` row with a synthetic email
and a ``guest`` identity keyed on the install. These pin the three moments
that make that safe:

* minting is idempotent on the install id, so a relaunch resumes the guest;
* a Google sign-in from a guest **links** when the address is new (same user
  id, so nothing downstream re-keys) and **merges** when it already has an
  account (every owned row moves, the guest row goes);
* the merge walks the schema for owner columns rather than a hand-kept list,
  and this file asserts the walk finds the tables a hand list would.

SQLite in memory. No network.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

import service.user_store as user_store
from models.auth import AuthIdentity, User
from models.membership import ProjectMember
from models.project import Project
from service.membership import ensure_owner_membership
from service.user_store import (
    GUEST_PROVIDER,
    _user_fk_columns,
    absorb_guest,
    get_or_create_guest,
    guest_email,
    is_guest_user,
    sweep_stale_guests,
    upsert_google_user,
)
from tests.conftest import make_sqlite_engine
from utils.dates import utcnow


@pytest.fixture
def engine(monkeypatch):
    engine = make_sqlite_engine(drop_partial_indexes=True)
    # SQLite ignores ON DELETE CASCADE unless asked; the sweep test below is
    # about the cascade, so ask.
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    monkeypatch.setattr(user_store, "get_engine", lambda: engine)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


def _google(email: str, *, sub: str = "", link: str | None = None):
    return upsert_google_user(
        provider_user_id=sub or f"sub-{email}",
        email=email,
        name="Ada",
        picture="",
        raw_profile={},
        link_user_id=link,
    )


def _project_for(db: Session, user_id: str, name: str = "Acme") -> Project:
    project = Project(user_id=UUID(user_id), name=name)
    db.add(project)
    db.flush()
    ensure_owner_membership(project, db)
    db.commit()
    return project


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------


def test_a_guest_is_minted_once_per_install(engine, db):
    first = get_or_create_guest("install-0001")
    second = get_or_create_guest("INSTALL-0001")  # case-folded, same install

    assert first.created is True
    assert second.created is False
    assert first.user_id == second.user_id
    assert first.email == guest_email("install-0001")

    row = db.get(User, UUID(first.user_id))
    assert is_guest_user(row)
    identity = db.execute(select(AuthIdentity).where(AuthIdentity.user_id == row.id)).scalars().one()
    assert (identity.provider, identity.provider_user_id) == (GUEST_PROVIDER, "install-0001")


@pytest.mark.parametrize("bad", ["", "short", "x" * 65, "has space", "Ünïcode-id"])
def test_an_install_id_is_validated_before_it_becomes_an_email(engine, bad):
    with pytest.raises(ValueError):
        get_or_create_guest(bad)


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------


def test_signing_in_from_a_guest_links_when_the_address_is_new(engine, db):
    guest = get_or_create_guest("install-link")
    project = _project_for(db, guest.user_id)

    result = _google("ada@example.com", link=guest.user_id)

    assert result.created is True, "first account for this person — a signup"
    assert result.user_id == guest.user_id, "the id must not change: nothing downstream re-keys"
    row = db.get(User, UUID(guest.user_id))
    db.refresh(row)
    assert row.email == "ada@example.com"
    assert not is_guest_user(row)
    providers = {
        i.provider for i in db.execute(select(AuthIdentity).where(AuthIdentity.user_id == row.id)).scalars()
    }
    assert providers == {"google"}, "the guest identity is dropped, the Google one attached"
    db.refresh(project)
    assert project.user_id == row.id


def test_a_link_id_that_is_not_a_guest_is_ignored(engine, db):
    victim = _google("victim@example.com")
    result = _google("attacker@example.com", link=victim.user_id)

    assert result.user_id != victim.user_id
    row = db.get(User, UUID(victim.user_id))
    assert row.email == "victim@example.com", "naming someone else's id must not touch their row"


def test_a_stale_or_garbage_link_id_is_ignored(engine):
    assert _google("a@example.com", link="not-a-uuid").created is True
    assert _google("b@example.com", link=str(uuid4())).created is True


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def test_signing_in_from_a_guest_merges_when_the_address_has_an_account(engine, db):
    existing = _google("ada@example.com")
    guest = get_or_create_guest("install-merge")
    guest_project = _project_for(db, guest.user_id, "Drafted while guest")

    result = _google("ada@example.com", link=guest.user_id)

    assert result.created is False
    assert result.user_id == existing.user_id
    assert db.get(User, UUID(guest.user_id)) is None, "the guest row goes"
    db.refresh(guest_project)
    assert str(guest_project.user_id) == existing.user_id
    member = db.execute(
        select(ProjectMember).where(ProjectMember.project_id == guest_project.id)
    ).scalars().one()
    assert str(member.user_id) == existing.user_id
    guest_identities = db.execute(
        select(AuthIdentity).where(AuthIdentity.provider == GUEST_PROVIDER)
    ).scalars().all()
    assert guest_identities == []


def test_a_merge_drops_a_guest_row_the_target_already_has(engine, db):
    """A membership the target holds already is theirs; the guest's copy is
    not moved on top of it — that would be a unique-constraint failure that
    rolled back the whole sign-in."""
    existing = _google("ada@example.com")
    guest = get_or_create_guest("install-clash")
    project = _project_for(db, guest.user_id)
    db.add(ProjectMember(project_id=project.id, user_id=UUID(existing.user_id), role="collaborator"))
    db.commit()

    with Session(engine) as session:
        absorb_guest(session, UUID(guest.user_id), UUID(existing.user_id))
        session.commit()

    rows = db.execute(select(ProjectMember).where(ProjectMember.project_id == project.id)).scalars().all()
    assert [str(r.user_id) for r in rows] == [existing.user_id]
    assert rows[0].role == "collaborator", "the target's own row survived, not the guest's"


def test_absorb_walks_every_owner_column_in_the_schema():
    """The merge is only as complete as this walk. If a table with an owner
    column is added and this fails, the fix is never to shorten the list."""
    found = {(table.name, column.name) for table, column in _user_fk_columns()}
    expected = {
        ("auth_identities", "user_id"),
        ("projects", "user_id"),
        ("project_members", "user_id"),
        ("artifacts", "user_id"),
        ("connector_credentials", "user_id"),
    }
    assert expected <= found


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def test_the_sweep_removes_only_guests_nobody_came_back_for(engine, db):
    stale = get_or_create_guest("install-stale")
    fresh = get_or_create_guest("install-fresh")
    linked = get_or_create_guest("install-linked")
    _google("kept@example.com", link=linked.user_id)
    stale_project_id = _project_for(db, stale.user_id).id

    old = utcnow() - timedelta(days=45)
    for uid in (stale.user_id, linked.user_id):
        row = db.get(User, UUID(uid))
        row.created_at = old
        db.add(row)
    db.commit()

    removed = sweep_stale_guests(db)
    db.commit()
    # The project was made through this session, so `get` would answer from
    # the identity map without asking the database whether it still exists.
    db.expire_all()

    assert removed == 1
    assert db.get(User, UUID(stale.user_id)) is None
    assert db.get(Project, stale_project_id) is None, "cascade takes the drafted project with it"
    assert db.get(User, UUID(fresh.user_id)) is not None
    assert db.get(User, UUID(linked.user_id)) is not None, "linked = a real account now, never swept"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.fixture
def client(engine, monkeypatch):
    import jwt as pyjwt
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routes.signin as signin
    import service.auth as auth_service
    from config import Configs

    secret = "test-secret-" + "x" * 32  # the validator wants 32+ characters
    cfg = Configs(jwt_secret=secret)
    monkeypatch.setattr(signin, "get_configs", lambda: cfg)
    # A fresh window per test: the limiter is module state and the burst test
    # below would otherwise leak into its neighbours.
    monkeypatch.setattr(signin, "_GUEST_LIMIT", type(signin._GUEST_LIMIT)(limit=3, window_seconds=60.0))

    app = FastAPI()
    app.include_router(signin.router)

    def current_user_from_bearer():
        # The real dependency needs a database session it cannot get here;
        # the token's `sub` is the email and that is enough to find the row.
        return app.state.user

    app.dependency_overrides[auth_service.get_current_user] = current_user_from_bearer
    client = TestClient(app, raise_server_exceptions=False)
    client.decode = lambda token: pyjwt.decode(token, secret, algorithms=["HS256"])
    client.app = app
    return client


def test_the_guest_route_returns_a_guest_token(client):
    res = client.post("/auth/guest", json={"install_id": "install-route-1"})
    assert res.status_code == 200, res.text
    body = res.json()
    claims = client.decode(body["token"])
    assert body["created"] is True
    assert claims["guest"] is True
    assert claims["new_user"] is True
    assert claims["sub"] == guest_email("install-route-1")
    assert claims["uid"]

    again = client.post("/auth/guest", json={"install_id": "install-route-1"}).json()
    assert again["created"] is False
    assert client.decode(again["token"])["uid"] == claims["uid"]


def test_the_guest_route_rejects_a_bad_install_id(client):
    assert client.post("/auth/guest", json={"install_id": "nope"}).status_code == 422


def test_the_guest_route_is_rate_limited_per_address(client):
    for i in range(3):
        assert client.post("/auth/guest", json={"install_id": f"install-burst-{i}"}).status_code == 200
    res = client.post("/auth/guest", json={"install_id": "install-burst-9"})
    assert res.status_code == 429
    assert "Retry-After" in res.headers


def test_a_link_code_is_only_for_guests(client, db):
    guest = get_or_create_guest("install-linkcode")
    client.app.state.user = db.get(User, UUID(guest.user_id))
    res = client.post("/auth/guest/link-code")
    assert res.status_code == 200 and res.json()["code"]

    member = _google("member@example.com")
    client.app.state.user = db.get(User, UUID(member.user_id))
    assert client.post("/auth/guest/link-code").status_code == 409
