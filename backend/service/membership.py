"""Project access checks and invitation token handling.

Every project route resolves access through one of the two helpers here rather
than comparing ``Project.user_id`` directly, so the owner-only rules and the
collaborator rules live in a single place.

Access model (see docs/engineering/project-collaboration-plan.md):

- **owner** — the creator. Full control, including inviting and removing
  members, deleting the project, and using their own connector credentials.
- **collaborator** — invited by the owner. Reads and edits the project, runs
  agents, works on content. Cannot manage members or delete the project.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from models.auth import User
from models.membership import (
    INVITE_PENDING,
    ROLE_COLLABORATOR,
    ROLE_OWNER,
    ProjectInvitation,
    ProjectMember,
)
from models.project import Project
from utils.dates import utcnow

# Length of the raw invitation token before URL-safe encoding. 32 bytes gives a
# 43-character token — far past guessing range for a link that also expires.
_TOKEN_BYTES = 32


# --- Token helpers -------------------------------------------------------


def generate_invitation_token() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hash)``. Only the hash is ever persisted."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    return token, hash_invitation_token(token)


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


# --- Membership queries --------------------------------------------------


def member_role(project_id: UUID, user_id: UUID, session: Session) -> str | None:
    """The caller's role on a project, or None when they have no access.

    Falls back to ``projects.user_id`` so a project whose owner row is somehow
    missing (a create that raced the member insert) still answers correctly for
    its owner.
    """
    row = session.execute(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).scalars().first()
    if row is not None:
        return row
    owner_id = session.execute(
        select(Project.user_id).where(Project.id == project_id)
    ).scalars().first()
    return ROLE_OWNER if owner_id == user_id else None


def accessible_projects(user: User, session: Session) -> list[Project]:
    """Every project the user owns or collaborates on, oldest first."""
    return list(
        session.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id)
            .order_by(Project.created_at)
        ).scalars().all()
    )


def get_project_for_user(
    project_id: UUID,
    user: User,
    session: Session,
    *,
    require_owner: bool = False,
) -> Project:
    """Load a project the caller may act on, or raise.

    404 when the caller has no access at all — a non-member must not be able to
    tell an existing project from a made-up id. 403 only once membership is
    established but the action is owner-only, which is a distinction the
    collaborator is entitled to see.
    """
    project = session.execute(
        select(Project).where(Project.id == project_id)
    ).scalars().first()
    if project is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    role = member_role(project_id, user.id, session)
    if role is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    if require_owner and role != ROLE_OWNER:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Only the project owner can perform this action.",
        )
    return project


def ensure_owner_membership(project: Project, session: Session) -> ProjectMember:
    """Idempotently give a project its owner row. Call after creating a project."""
    existing = session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == project.user_id,
        )
    ).scalars().first()
    if existing is not None:
        if existing.role != ROLE_OWNER:
            existing.role = ROLE_OWNER
            existing.updated_at = utcnow()
            session.add(existing)
        return existing

    member = ProjectMember(
        project_id=project.id,
        user_id=project.user_id,
        role=ROLE_OWNER,
    )
    session.add(member)
    return member


def project_owner(project: Project, session: Session) -> User | None:
    return session.execute(
        select(User).where(User.id == project.user_id)
    ).scalars().first()


# --- Invitations ---------------------------------------------------------


def invitation_expiry(ttl_days: int) -> datetime:
    return utcnow() + timedelta(days=ttl_days)


def is_invitation_live(invitation: ProjectInvitation) -> bool:
    """Pending and not past its expiry."""
    if invitation.status != INVITE_PENDING:
        return False
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > utcnow()


def find_live_invitation(token: str, session: Session) -> ProjectInvitation | None:
    """Resolve a plaintext token to a redeemable invitation, or None."""
    invitation = session.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.token_hash == hash_invitation_token(token)
        )
    ).scalars().first()
    if invitation is None or not is_invitation_live(invitation):
        return None
    return invitation


def add_collaborator(
    project_id: UUID,
    user_id: UUID,
    session: Session,
    *,
    invited_by_user_id: UUID | None = None,
) -> ProjectMember:
    """Add (or return an existing) membership row. Never demotes an owner."""
    existing = session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).scalars().first()
    if existing is not None:
        return existing

    member = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=ROLE_COLLABORATOR,
        invited_by_user_id=invited_by_user_id,
    )
    session.add(member)
    return member
