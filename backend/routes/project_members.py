"""Project collaboration endpoints — members and email invitations.

Two routers:

- ``router`` mounts under ``/api/user/projects`` and manages the member list of
  one project (view, invite, revoke, resend, remove/leave).
- ``invitation_router`` mounts under ``/api/invitations`` and handles redeeming
  a token: an unauthenticated preview so the landing page can say who invited
  you before you sign in, and an authenticated accept.

Owner-only actions are enforced through ``get_project_for_user(..., require_owner=True)``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from config import Configs, get_configs
from db.session import get_session
from models.auth import User
from models.membership import (
    INVITE_ACCEPTED,
    INVITE_PENDING,
    INVITE_REVOKED,
    ROLE_COLLABORATOR,
    ROLE_OWNER,
    ProjectInvitation,
    ProjectMember,
)
from models.project import Project
from service.auth import get_current_user
from service.email import active_backend, send_email
from service.email.templates import invitation_accepted, project_invitation
from service.membership import (
    add_collaborator,
    find_live_invitation,
    generate_invitation_token,
    get_project_for_user,
    invitation_expiry,
    is_invitation_live,
    member_role,
    normalize_email,
    project_owner,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["project-members"])
invitation_router = APIRouter(tags=["project-invitations"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Response shapes -----------------------------------------------------


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    full_name: str = ""
    avatar_url: str = ""
    role: str
    joined_at: str
    is_you: bool = False


class InvitationOut(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    expires_at: str
    created_at: str
    last_sent_at: str = ""
    invited_by_email: str = ""
    # False once expires_at has passed; the row stays 'pending' until it is
    # resent or revoked, so the UI needs the derived flag to label it.
    is_expired: bool = False


class MembersResponse(BaseModel):
    project_id: UUID
    project_name: str
    viewer_role: str
    members: list[MemberOut]
    invitations: list[InvitationOut]
    # Echoed so the UI can warn when invites are only being logged, not sent.
    email_delivery: str = "console"


# Deliberately permissive: this is a typo guard, not an RFC 5322 parser. The
# real verification is that the invite only works for whoever can read the
# mailbox. Avoids pulling in email-validator for one field.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class InviteIn(BaseModel):
    email: str

    @field_validator("email", mode="after")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        email = v.strip().lower()
        if not _EMAIL_RE.match(email) or len(email) > 254:
            raise ValueError("Enter a valid email address.")
        return email


class InvitePreviewOut(BaseModel):
    project_name: str
    invited_email: str
    inviter_name: str = ""
    inviter_email: str = ""
    role: str = ROLE_COLLABORATOR
    expires_at: str = ""


class AcceptOut(BaseModel):
    project_id: UUID
    project_name: str
    role: str


def _invite_url(token: str, cfg: Configs) -> str:
    return f"{cfg.frontend_origin.rstrip('/')}/invite/{token}"


def _members_url(project_id: UUID, cfg: Configs) -> str:
    return f"{cfg.frontend_origin.rstrip('/')}/project/{project_id}/members"


def _to_invitation_out(inv: ProjectInvitation, inviter_email: str = "") -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role,
        status=inv.status,
        expires_at=inv.expires_at.isoformat(),
        created_at=inv.created_at.isoformat(),
        last_sent_at=inv.last_sent_at.isoformat() if inv.last_sent_at else "",
        invited_by_email=inviter_email,
        is_expired=inv.status == INVITE_PENDING and not is_invitation_live(inv),
    )


def _users_by_id(user_ids: set[UUID], session: Session) -> dict[UUID, User]:
    if not user_ids:
        return {}
    rows = session.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    return {u.id: u for u in rows}


# --- Member list ---------------------------------------------------------


@router.get("/{project_id}/members")
def list_members(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    cfg: Configs = Depends(get_configs),
) -> MembersResponse:
    """Members and pending invitations. Collaborators can see who else is on
    the project — hiding that would make the shared workspace confusing — but
    only the owner can change the list."""
    project = get_project_for_user(project_id, user, session)
    viewer_role = member_role(project_id, user.id, session) or ROLE_COLLABORATOR

    member_rows = session.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    ).scalars().all()
    invitation_rows = session.execute(
        select(ProjectInvitation)
        .where(
            ProjectInvitation.project_id == project_id,
            ProjectInvitation.status == INVITE_PENDING,
        )
        .order_by(ProjectInvitation.created_at)
    ).scalars().all()

    referenced = {m.user_id for m in member_rows}
    referenced |= {i.invited_by_user_id for i in invitation_rows if i.invited_by_user_id}
    referenced.add(project.user_id)
    users = _users_by_id(referenced, session)

    members = [
        MemberOut(
            user_id=m.user_id,
            email=users[m.user_id].email if m.user_id in users else "",
            full_name=(users[m.user_id].full_name or "") if m.user_id in users else "",
            avatar_url=(users[m.user_id].avatar_url or "") if m.user_id in users else "",
            role=m.role,
            joined_at=m.created_at.isoformat(),
            is_you=m.user_id == user.id,
        )
        for m in member_rows
    ]
    # Owner first, then collaborators in join order.
    members.sort(key=lambda m: (0 if m.role == ROLE_OWNER else 1, m.joined_at))

    return MembersResponse(
        project_id=project_id,
        project_name=project.name,
        viewer_role=viewer_role,
        members=members,
        invitations=[
            _to_invitation_out(
                inv,
                users[inv.invited_by_user_id].email
                if inv.invited_by_user_id in users
                else "",
            )
            for inv in invitation_rows
        ],
        email_delivery=active_backend(cfg),
    )


# --- Invitations ---------------------------------------------------------


async def _send_invitation(
    invitation: ProjectInvitation,
    token: str,
    project: Project,
    inviter: User,
    cfg: Configs,
) -> bool:
    message = project_invitation(
        project_name=project.name,
        inviter_name=inviter.full_name or "",
        inviter_email=inviter.email,
        accept_url=_invite_url(token, cfg),
        expires_in_days=cfg.invitation_ttl_days,
        recipient_email=invitation.email,
    )
    result = await send_email(message, cfg)
    if not result.delivered:
        logger.warning(
            "Invitation email not delivered (project=%s invitation=%s): %s",
            project.id,
            invitation.id,
            result.error,
        )
    return result.delivered


@router.post("/{project_id}/invitations", status_code=201)
async def create_invitation(
    project_id: UUID,
    body: InviteIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    cfg: Configs = Depends(get_configs),
) -> InvitationOut:
    """Invite an email address to collaborate. Owner only."""
    project = get_project_for_user(project_id, user, session, require_owner=True)
    email = normalize_email(body.email)

    if email == normalize_email(user.email):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="You already have access to this project.",
        )

    # Already a member? Say so rather than sending an invite that resolves to a no-op.
    existing_user = session.execute(
        select(User).where(User.email == email)
    ).scalars().first()
    if existing_user is not None and member_role(project_id, existing_user.id, session):
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=f"{email} is already a member of this project.",
        )

    # Reuse the pending row for this address: a re-invite should refresh the
    # token and expiry, not stack up rows the owner has to reconcile.
    invitation = session.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.project_id == project_id,
            ProjectInvitation.email == email,
            ProjectInvitation.status == INVITE_PENDING,
        )
    ).scalars().first()

    token, token_hash = generate_invitation_token()
    now = _utcnow()
    if invitation is None:
        invitation = ProjectInvitation(
            project_id=project_id,
            email=email,
            role=ROLE_COLLABORATOR,
            token_hash=token_hash,
            invited_by_user_id=user.id,
            expires_at=invitation_expiry(cfg.invitation_ttl_days),
            last_sent_at=now,
        )
    else:
        invitation.token_hash = token_hash
        invitation.invited_by_user_id = user.id
        invitation.expires_at = invitation_expiry(cfg.invitation_ttl_days)
        invitation.last_sent_at = now
        invitation.updated_at = now
    session.add(invitation)
    session.commit()
    session.refresh(invitation)

    await _send_invitation(invitation, token, project, user, cfg)
    return _to_invitation_out(invitation, user.email)


@router.post("/{project_id}/invitations/{invitation_id}/resend")
async def resend_invitation(
    project_id: UUID,
    invitation_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    cfg: Configs = Depends(get_configs),
) -> InvitationOut:
    """Re-send a pending invite with a fresh token and expiry. Owner only.

    The old token stops working — a resend is a replacement, not a duplicate.
    """
    project = get_project_for_user(project_id, user, session, require_owner=True)
    invitation = session.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.project_id == project_id,
        )
    ).scalars().first()
    if invitation is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.status != INVITE_PENDING:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=f"This invitation was already {invitation.status}.",
        )

    token, token_hash = generate_invitation_token()
    invitation.token_hash = token_hash
    invitation.expires_at = invitation_expiry(cfg.invitation_ttl_days)
    invitation.last_sent_at = _utcnow()
    invitation.updated_at = _utcnow()
    session.add(invitation)
    session.commit()
    session.refresh(invitation)

    await _send_invitation(invitation, token, project, user, cfg)
    return _to_invitation_out(invitation, user.email)


@router.delete("/{project_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    project_id: UUID,
    invitation_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Revoke a pending invite. Owner only. The row is kept as history so the
    token can never be redeemed again."""
    get_project_for_user(project_id, user, session, require_owner=True)
    invitation = session.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.project_id == project_id,
        )
    ).scalars().first()
    if invitation is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.status != INVITE_PENDING:
        return

    invitation.status = INVITE_REVOKED
    invitation.updated_at = _utcnow()
    session.add(invitation)
    session.commit()


# --- Member removal ------------------------------------------------------


@router.delete("/{project_id}/members/{member_user_id}", status_code=204)
def remove_member(
    project_id: UUID,
    member_user_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Remove a collaborator. The owner can remove anyone; a collaborator can
    remove only themselves (``member_user_id`` of ``me``), which is how you
    leave a shared project. The owner row can never be removed — deleting the
    project is the owner's exit."""
    role = member_role(project_id, user.id, session)
    if role is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")

    if member_user_id == "me":
        target_id = user.id
    else:
        try:
            target_id = UUID(member_user_id)
        except ValueError:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Member not found") from None

    if target_id != user.id and role != ROLE_OWNER:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Only the project owner can remove other members.",
        )

    membership = session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target_id,
        )
    ).scalars().first()
    if membership is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Member not found")
    if membership.role == ROLE_OWNER:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="The project owner cannot be removed. Delete the project instead.",
        )

    session.delete(membership)
    session.commit()


# --- Redeeming an invitation --------------------------------------------


@invitation_router.get("/{token}")
def preview_invitation(
    token: str,
    session: Session = Depends(get_session),
) -> InvitePreviewOut:
    """What the invite landing page shows before sign-in.

    Unauthenticated by design — the recipient has not signed in yet. The token
    is the secret, so this only ever reveals the project name and inviter to
    someone who already holds the emailed link.
    """
    invitation = find_live_invitation(token, session)
    if invitation is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="This invitation link is invalid, expired, or has already been used.",
        )

    project = session.execute(
        select(Project).where(Project.id == invitation.project_id)
    ).scalars().first()
    inviter = (
        session.execute(
            select(User).where(User.id == invitation.invited_by_user_id)
        ).scalars().first()
        if invitation.invited_by_user_id
        else None
    )

    return InvitePreviewOut(
        project_name=project.name if project else "",
        invited_email=invitation.email,
        inviter_name=(inviter.full_name or "") if inviter else "",
        inviter_email=inviter.email if inviter else "",
        role=invitation.role,
        expires_at=invitation.expires_at.isoformat(),
    )


@invitation_router.post("/{token}/accept")
async def accept_invitation(
    token: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    cfg: Configs = Depends(get_configs),
) -> AcceptOut:
    """Redeem an invitation as the signed-in user.

    The signed-in address must match the invited one. Anything looser would let
    a forwarded link grant access to whoever opened it.
    """
    invitation = find_live_invitation(token, session)
    if invitation is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="This invitation link is invalid, expired, or has already been used.",
        )
    if normalize_email(user.email) != invitation.email:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=(
                f"This invitation was sent to {invitation.email}. "
                f"Sign in with that address to accept it."
            ),
        )

    project = session.execute(
        select(Project).where(Project.id == invitation.project_id)
    ).scalars().first()
    if project is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="This project no longer exists."
        )

    already_member = member_role(project.id, user.id, session) is not None
    add_collaborator(
        project.id,
        user.id,
        session,
        invited_by_user_id=invitation.invited_by_user_id,
    )
    now = _utcnow()
    invitation.status = INVITE_ACCEPTED
    invitation.accepted_at = now
    invitation.accepted_by_user_id = user.id
    invitation.updated_at = now
    session.add(invitation)
    session.commit()

    role = member_role(project.id, user.id, session) or ROLE_COLLABORATOR

    if not already_member:
        owner = project_owner(project, session)
        if owner is not None and normalize_email(owner.email) != normalize_email(user.email):
            await send_email(
                invitation_accepted(
                    project_name=project.name,
                    member_name=user.full_name or "",
                    member_email=user.email,
                    project_url=_members_url(project.id, cfg),
                    recipient_email=owner.email,
                ),
                cfg,
            )

    return AcceptOut(project_id=project.id, project_name=project.name, role=role)
