"""Tests for project collaboration — membership access rules and invitations.

Runs offline against SQLite. Postgres-only DDL (JSONB, partial indexes) is
adapted below rather than skipped, because the value here is in the permission
boundaries and the invite state machine, both of which are pure application
logic. The Postgres-specific guarantees these tests can't cover — the
single-owner partial index and the one-pending-invite-per-email index — are
enforced by the migration and exercised against a real database in staging.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


from config import Configs, get_configs  # noqa: E402
from db.session import get_session  # noqa: E402
from models.auth import User  # noqa: E402
from models.membership import (  # noqa: E402
    INVITE_ACCEPTED,
    INVITE_PENDING,
    INVITE_REVOKED,
    ROLE_COLLABORATOR,
    ROLE_OWNER,
    ProjectInvitation,
    ProjectMember,
)
from models.project import Project  # noqa: E402
from routes import project_members, user_projects  # noqa: E402
from service.auth import get_current_user  # noqa: E402
from service.membership import (  # noqa: E402
    generate_invitation_token,
    hash_invitation_token,
    member_role,
    normalize_email,
)

TEST_ORIGIN = "http://localhost:3003"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _Harness:
    """A FastAPI app wired to a throwaway SQLite DB, with the signed-in user
    swappable per request via ``as_user``."""

    def __init__(self, session: Session, app: FastAPI, client: TestClient):
        self.session = session
        self.app = app
        self.client = client
        self.current_user: User | None = None
        self.sent: list = []

    def as_user(self, user: User | None) -> None:
        self.current_user = user


@pytest.fixture
def harness(monkeypatch):
    # StaticPool + check_same_thread=False: TestClient runs sync handlers on a
    # worker thread, and without a shared connection each thread would get its
    # own empty :memory: database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    # SQLite has no partial indexes here: SQLAlchemy drops the `postgresql_where`
    # clause for other dialects, turning "one owner per project" and "one pending
    # invite per address" into unconditional UNIQUE constraints that would reject
    # legitimate rows. Drop them so these tests exercise the application logic;
    # Postgres keeps them as the real backstop.
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX IF EXISTS uq_project_members_single_owner")
        conn.exec_driver_sql("DROP INDEX IF EXISTS uq_project_invitations_pending_email")
    session = Session(engine)

    app = FastAPI()
    app.include_router(user_projects.router, prefix="/api/user/projects")
    app.include_router(project_members.router, prefix="/api/user/projects")
    app.include_router(project_members.invitation_router, prefix="/api/invitations")

    cfg = Configs(
        frontend_origin=TEST_ORIGIN,
        resend_api_key="",  # console backend — nothing leaves the process
        invitation_ttl_days=7,
    )

    state = _Harness(session, app, None)  # type: ignore[arg-type]

    def _session_override():
        yield session

    def _user_override():
        if state.current_user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Not authenticated")
        return state.current_user

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_user] = _user_override
    app.dependency_overrides[get_configs] = lambda: cfg

    # Capture outbound mail instead of logging it, so tests can assert on the
    # rendered message (and on the invite URL, which carries the only copy of
    # the plaintext token).
    async def _capture(message, config=None):  # noqa: ANN001, ARG001
        from service.email.sender import EmailResult

        state.sent.append(message)
        return EmailResult(delivered=True, backend="console")

    monkeypatch.setattr(project_members, "send_email", _capture)

    state.client = TestClient(app, raise_server_exceptions=False)
    yield state

    session.close()
    engine.dispose()


def make_user(session: Session, email: str, name: str = "") -> User:
    user = User(email=normalize_email(email), full_name=name or email.split("@")[0])
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_project(session: Session, owner: User, name: str = "Acme Growth") -> Project:
    project = Project(user_id=owner.id, name=name)
    session.add(project)
    session.commit()
    session.refresh(project)
    session.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ROLE_OWNER))
    session.commit()
    return project


def _rows(session: Session, model):
    from sqlalchemy import select

    return list(session.execute(select(model)).scalars().all())


def _one(session: Session, model):
    rows = _rows(session, model)
    assert len(rows) == 1, f"expected exactly one {model.__name__}, got {len(rows)}"
    return rows[0]


def _count(session: Session, model) -> int:
    return len(_rows(session, model))


def token_from_last_email(harness: _Harness) -> str:
    """Pull the invite token out of the accept URL in the most recent email."""
    assert harness.sent, "no email was sent"
    marker = f"{TEST_ORIGIN}/invite/"
    text = harness.sent[-1].text
    start = text.index(marker) + len(marker)
    return text[start:].split()[0].strip()


# ---------------------------------------------------------------------------
# Token handling
# ---------------------------------------------------------------------------


def test_generated_token_is_stored_only_as_a_hash():
    token, digest = generate_invitation_token()
    assert token != digest
    assert digest == hash_invitation_token(token)
    assert len(token) >= 32
    # Two calls never collide.
    assert generate_invitation_token()[0] != token


def test_normalize_email_lowercases_and_trims():
    assert normalize_email("  Ana@Acme.COM ") == "ana@acme.com"


# ---------------------------------------------------------------------------
# Invite lifecycle
# ---------------------------------------------------------------------------


def test_owner_invites_and_collaborator_accepts(harness):
    owner = make_user(harness.session, "owner@acme.com", "Owner Person")
    project = make_project(harness.session, owner)

    harness.as_user(owner)
    res = harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "Ana@Acme.com"}
    )
    assert res.status_code == 201, res.text
    assert res.json()["email"] == "ana@acme.com"
    assert res.json()["status"] == INVITE_PENDING

    # The invite email carries the only copy of the plaintext token.
    token = token_from_last_email(harness)
    assert harness.sent[-1].to == "ana@acme.com"
    assert "Owner Person invited you" in harness.sent[-1].subject

    # Preview works before the invitee has signed in.
    harness.as_user(None)
    preview = harness.client.get(f"/api/invitations/{token}")
    assert preview.status_code == 200, preview.text
    assert preview.json()["project_name"] == "Acme Growth"
    assert preview.json()["invited_email"] == "ana@acme.com"
    assert preview.json()["inviter_email"] == "owner@acme.com"

    ana = make_user(harness.session, "ana@acme.com", "Ana")
    harness.as_user(ana)
    accepted = harness.client.post(f"/api/invitations/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == ROLE_COLLABORATOR
    assert member_role(project.id, ana.id, harness.session) == ROLE_COLLABORATOR

    # The owner is told someone joined.
    assert harness.sent[-1].to == "owner@acme.com"
    assert "Ana joined" in harness.sent[-1].subject

    # The project now shows up in the collaborator's project list, flagged as shared.
    listed = harness.client.get("/api/user/projects").json()
    assert [p["id"] for p in listed] == [str(project.id)]
    assert listed[0]["role"] == ROLE_COLLABORATOR
    assert listed[0]["owner_email"] == "owner@acme.com"


def test_token_is_single_use(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    harness.as_user(owner)
    harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
    )
    token = token_from_last_email(harness)

    ana = make_user(harness.session, "ana@acme.com")
    harness.as_user(ana)
    assert harness.client.post(f"/api/invitations/{token}/accept").status_code == 200
    replay = harness.client.post(f"/api/invitations/{token}/accept")
    assert replay.status_code == 404


def test_accept_requires_the_invited_address(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    harness.as_user(owner)
    harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
    )
    token = token_from_last_email(harness)

    # A forwarded link must not grant access to whoever opens it.
    interloper = make_user(harness.session, "someone.else@acme.com")
    harness.as_user(interloper)
    res = harness.client.post(f"/api/invitations/{token}/accept")
    assert res.status_code == 403
    assert "ana@acme.com" in res.json()["detail"]
    assert member_role(project.id, interloper.id, harness.session) is None


def test_expired_invitation_cannot_be_previewed_or_accepted(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    harness.as_user(owner)
    harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
    )
    token = token_from_last_email(harness)

    invitation = _one(harness.session, ProjectInvitation)
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    harness.session.add(invitation)
    harness.session.commit()

    harness.as_user(None)
    assert harness.client.get(f"/api/invitations/{token}").status_code == 404

    ana = make_user(harness.session, "ana@acme.com")
    harness.as_user(ana)
    assert harness.client.post(f"/api/invitations/{token}/accept").status_code == 404


def test_revoked_invitation_stops_working(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    harness.as_user(owner)
    created = harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
    ).json()
    token = token_from_last_email(harness)

    revoked = harness.client.delete(
        f"/api/user/projects/{project.id}/invitations/{created['id']}"
    )
    assert revoked.status_code == 204
    assert _one(harness.session, ProjectInvitation).status == INVITE_REVOKED

    ana = make_user(harness.session, "ana@acme.com")
    harness.as_user(ana)
    assert harness.client.post(f"/api/invitations/{token}/accept").status_code == 404


def test_resend_replaces_the_old_token(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    harness.as_user(owner)
    created = harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
    ).json()
    first_token = token_from_last_email(harness)

    res = harness.client.post(
        f"/api/user/projects/{project.id}/invitations/{created['id']}/resend"
    )
    assert res.status_code == 200, res.text
    second_token = token_from_last_email(harness)
    assert second_token != first_token
    # Still one invitation, not two.
    assert _count(harness.session, ProjectInvitation) == 1

    ana = make_user(harness.session, "ana@acme.com")
    harness.as_user(ana)
    assert harness.client.post(f"/api/invitations/{first_token}/accept").status_code == 404
    assert harness.client.post(f"/api/invitations/{second_token}/accept").status_code == 200


def test_reinviting_a_pending_address_refreshes_rather_than_duplicates(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    harness.as_user(owner)
    first = harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
    ).json()
    second = harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ANA@acme.com"}
    ).json()
    assert first["id"] == second["id"]
    assert _count(harness.session, ProjectInvitation) == 1


def test_cannot_invite_yourself_or_an_existing_member(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    ana = make_user(harness.session, "ana@acme.com")
    harness.session.add(
        ProjectMember(project_id=project.id, user_id=ana.id, role=ROLE_COLLABORATOR)
    )
    harness.session.commit()

    harness.as_user(owner)
    assert (
        harness.client.post(
            f"/api/user/projects/{project.id}/invitations", json={"email": "owner@acme.com"}
        ).status_code
        == 400
    )
    assert (
        harness.client.post(
            f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
        ).status_code
        == 409
    )


def test_malformed_email_is_rejected(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    harness.as_user(owner)
    res = harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "not-an-email"}
    )
    assert res.status_code == 422


def test_accepting_when_already_a_member_is_a_no_op(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    ana = make_user(harness.session, "ana@acme.com")

    harness.as_user(owner)
    harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "ana@acme.com"}
    )
    token = token_from_last_email(harness)
    harness.session.add(
        ProjectMember(project_id=project.id, user_id=ana.id, role=ROLE_COLLABORATOR)
    )
    harness.session.commit()

    harness.as_user(ana)
    res = harness.client.post(f"/api/invitations/{token}/accept")
    assert res.status_code == 200
    assert res.json()["role"] == ROLE_COLLABORATOR
    assert _count(harness.session, ProjectMember) == 2
    assert _one(harness.session, ProjectInvitation).status == INVITE_ACCEPTED


# ---------------------------------------------------------------------------
# Permission boundaries
# ---------------------------------------------------------------------------


def add_collaborator_to(harness, project, email="ana@acme.com") -> User:
    user = make_user(harness.session, email)
    harness.session.add(
        ProjectMember(project_id=project.id, user_id=user.id, role=ROLE_COLLABORATOR)
    )
    harness.session.commit()
    return user


def test_collaborator_can_read_and_edit_but_not_invite_or_delete(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    ana = add_collaborator_to(harness, project)

    harness.as_user(ana)
    assert harness.client.get(f"/api/user/projects/{project.id}").status_code == 200

    edited = harness.client.put(
        f"/api/user/projects/{project.id}", json={"name": "Renamed by Ana"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Renamed by Ana"
    assert edited.json()["role"] == ROLE_COLLABORATOR

    assert (
        harness.client.post(
            f"/api/user/projects/{project.id}/invitations", json={"email": "bob@acme.com"}
        ).status_code
        == 403
    )
    assert harness.client.delete(f"/api/user/projects/{project.id}").status_code == 403


def test_non_member_gets_404_not_403(harness):
    """A stranger must not be able to tell a real project id from a fake one."""
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    stranger = make_user(harness.session, "stranger@example.com")

    harness.as_user(stranger)
    assert harness.client.get(f"/api/user/projects/{project.id}").status_code == 404
    assert harness.client.get(f"/api/user/projects/{project.id}/members").status_code == 404
    assert harness.client.delete(f"/api/user/projects/{project.id}").status_code == 404


def test_put_does_not_let_a_stranger_overwrite_an_existing_project(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    stranger = make_user(harness.session, "stranger@example.com")

    harness.as_user(stranger)
    res = harness.client.put(
        f"/api/user/projects/{project.id}", json={"name": "Hijacked"}
    )
    assert res.status_code == 404
    harness.session.expire_all()
    assert harness.session.get(Project, project.id).name == "Acme Growth"


def test_put_with_an_unclaimed_id_creates_a_project_owned_by_the_caller(harness):
    user = make_user(harness.session, "solo@acme.com")
    harness.as_user(user)
    new_id = uuid4()
    res = harness.client.put(f"/api/user/projects/{new_id}", json={"name": "Fresh"})
    assert res.status_code == 200, res.text
    assert res.json()["role"] == ROLE_OWNER
    assert member_role(new_id, user.id, harness.session) == ROLE_OWNER


def test_members_list_shows_owner_first_and_pending_invites(harness):
    owner = make_user(harness.session, "owner@acme.com", "Owner Person")
    project = make_project(harness.session, owner)
    ana = add_collaborator_to(harness, project)

    harness.as_user(owner)
    harness.client.post(
        f"/api/user/projects/{project.id}/invitations", json={"email": "bob@acme.com"}
    )

    body = harness.client.get(f"/api/user/projects/{project.id}/members").json()
    assert body["viewer_role"] == ROLE_OWNER
    assert [m["email"] for m in body["members"]] == ["owner@acme.com", "ana@acme.com"]
    assert body["members"][0]["role"] == ROLE_OWNER
    assert body["members"][0]["is_you"] is True
    assert [i["email"] for i in body["invitations"]] == ["bob@acme.com"]
    assert body["invitations"][0]["invited_by_email"] == "owner@acme.com"
    # Console backend in tests — the UI uses this to warn that mail is not leaving.
    assert body["email_delivery"] == "console"

    # A collaborator sees the same roster but is labelled as one.
    harness.as_user(ana)
    ana_view = harness.client.get(f"/api/user/projects/{project.id}/members").json()
    assert ana_view["viewer_role"] == ROLE_COLLABORATOR
    assert len(ana_view["members"]) == 2


# ---------------------------------------------------------------------------
# Removal / leaving
# ---------------------------------------------------------------------------


def test_owner_removes_a_collaborator(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    ana = add_collaborator_to(harness, project)

    harness.as_user(owner)
    res = harness.client.delete(f"/api/user/projects/{project.id}/members/{ana.id}")
    assert res.status_code == 204
    assert member_role(project.id, ana.id, harness.session) is None

    harness.as_user(ana)
    assert harness.client.get(f"/api/user/projects/{project.id}").status_code == 404


def test_collaborator_can_leave_but_not_remove_others(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)
    ana = add_collaborator_to(harness, project, "ana@acme.com")
    bob = add_collaborator_to(harness, project, "bob@acme.com")

    harness.as_user(ana)
    assert (
        harness.client.delete(f"/api/user/projects/{project.id}/members/{bob.id}").status_code
        == 403
    )
    assert (
        harness.client.delete(f"/api/user/projects/{project.id}/members/me").status_code == 204
    )
    assert member_role(project.id, ana.id, harness.session) is None
    assert member_role(project.id, bob.id, harness.session) == ROLE_COLLABORATOR


def test_owner_cannot_be_removed(harness):
    owner = make_user(harness.session, "owner@acme.com")
    project = make_project(harness.session, owner)

    harness.as_user(owner)
    for target in (str(owner.id), "me"):
        res = harness.client.delete(f"/api/user/projects/{project.id}/members/{target}")
        assert res.status_code == 400
        assert "owner cannot be removed" in res.json()["detail"]
    assert member_role(project.id, owner.id, harness.session) == ROLE_OWNER


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------


def test_invitation_template_escapes_project_names():
    from service.email.templates import project_invitation

    message = project_invitation(
        project_name='<script>alert("x")</script>',
        inviter_name="Owner",
        inviter_email="owner@acme.com",
        accept_url="https://app.example/invite/abc",
        expires_in_days=7,
        recipient_email="ana@acme.com",
    )
    assert "<script>" not in message.html
    assert "&lt;script&gt;" in message.html
    assert "https://app.example/invite/abc" in message.html
    assert "https://app.example/invite/abc" in message.text
    assert message.reply_to == "owner@acme.com"


def test_invitation_template_says_one_day_for_a_one_day_ttl():
    from service.email.templates import project_invitation

    message = project_invitation(
        project_name="Acme",
        inviter_name="",
        inviter_email="owner@acme.com",
        accept_url="https://app.example/invite/abc",
        expires_in_days=1,
        recipient_email="ana@acme.com",
    )
    assert "expires in 1 day " in message.text
    # Falls back to the inviter's email when they have no display name.
    assert message.subject.startswith("owner@acme.com invited you")


@pytest.mark.asyncio
async def test_console_backend_reports_delivery_without_a_provider():
    from service.email import active_backend, send_email
    from service.email.sender import EmailMessage

    cfg = Configs(resend_api_key="")
    assert active_backend(cfg) == "console"
    result = await send_email(
        EmailMessage(to="ana@acme.com", subject="s", html="<p>h</p>", text="t"), cfg
    )
    assert result.delivered is True
    assert result.backend == "console"


def test_resend_backend_is_selected_when_a_key_is_present():
    from service.email import active_backend

    assert active_backend(Configs(resend_api_key="re_test")) == "resend"
