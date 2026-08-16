"""User project CRUD — GET/POST/PUT/DELETE /api/user/projects."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlmodel import Session

from db.session import get_session
from models.auth import User
from models.membership import ROLE_COLLABORATOR, ROLE_OWNER
from models.project import Project
from service.auth import get_current_user
from service.membership import (
    accessible_projects,
    ensure_owner_membership,
    get_project_for_user,
    member_role,
)

router = APIRouter(tags=["user-projects"])


_JSONB_MAX_BYTES = 128_000


class ProjectIn(BaseModel):
    name: str
    company_name: str = ""
    pitch: str = ""
    industry: str = ""
    business_model: str = ""
    website_url: str = ""
    targets: dict = {}
    audience: dict = {}
    competition: dict = {}
    brand_channels: dict = {}

    @field_validator("targets", "audience", "competition", "brand_channels", mode="after")
    @classmethod
    def _check_size(cls, v: dict) -> dict:
        if len(json.dumps(v)) > _JSONB_MAX_BYTES:
            raise ValueError("Section payload too large (max 128 KB).")
        return v


class ProjectOut(BaseModel):
    id: UUID
    name: str
    company_name: str
    pitch: str
    industry: str
    business_model: str
    website_url: str
    targets: dict
    audience: dict
    competition: dict
    brand_channels: dict
    created_at: str
    updated_at: str
    # Caller's relationship to this project. The app uses it to label shared
    # projects and to hide owner-only controls (invite, remove, delete).
    role: str = ROLE_OWNER
    owner_email: str = ""


def _to_out(p: Project, *, role: str = ROLE_OWNER, owner_email: str = "") -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        company_name=p.company_name,
        pitch=p.pitch,
        industry=p.industry,
        business_model=p.business_model,
        website_url=p.url,
        targets=p.targets or {},
        audience=p.audience or {},
        competition=p.competition or {},
        brand_channels=p.brand_channels or {},
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
        role=role,
        owner_email=owner_email,
    )


def _owner_emails(projects: list[Project], session: Session) -> dict[UUID, str]:
    """Owner email per project id, in one query rather than N."""
    owner_ids = {p.user_id for p in projects}
    if not owner_ids:
        return {}
    rows = session.execute(
        select(User.id, User.email).where(User.id.in_(owner_ids))
    ).all()
    by_user = {user_id: email for user_id, email in rows}
    return {p.id: by_user.get(p.user_id, "") for p in projects}


@router.get("")
def list_projects(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ProjectOut]:
    """Projects the caller owns plus those they have been invited to."""
    rows = accessible_projects(user, session)
    emails = _owner_emails(rows, session)
    return [
        _to_out(
            r,
            role=ROLE_OWNER if r.user_id == user.id else ROLE_COLLABORATOR,
            owner_email=emails.get(r.id, ""),
        )
        for r in rows
    ]


@router.post("", status_code=201)
def create_project(
    body: ProjectIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProjectOut:
    project = Project(
        user_id=user.id,
        name=body.name,
        company_name=body.company_name,
        pitch=body.pitch,
        industry=body.industry,
        business_model=body.business_model,
        url=body.website_url,
        targets=body.targets,
        audience=body.audience,
        competition=body.competition,
        brand_channels=body.brand_channels,
    )
    session.add(project)
    session.flush()
    ensure_owner_membership(project, session)
    session.commit()
    session.refresh(project)
    return _to_out(project, role=ROLE_OWNER, owner_email=user.email)


@router.get("/{project_id}")
def get_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProjectOut:
    project = get_project_for_user(project_id, user, session)
    return _to_out(
        project,
        role=member_role(project_id, user.id, session) or ROLE_COLLABORATOR,
        owner_email=_owner_emails([project], session).get(project.id, ""),
    )


@router.put("/{project_id}")
def update_project(
    project_id: UUID,
    body: ProjectIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProjectOut:
    """Upsert by client-supplied id.

    The frontend generates project UUIDs locally (and already references them
    from content plans / agent contexts), so a missing project is created with
    the supplied id rather than 404'd — keeping those references valid.

    Collaborators may edit an existing project; the create branch only runs for
    ids that belong to nobody, and the caller becomes its owner.
    """
    from datetime import datetime, timezone

    existing = session.execute(
        select(Project).where(Project.id == project_id)
    ).scalars().first()
    is_new = existing is None
    if is_new:
        project = Project(id=project_id, user_id=user.id)
        session.add(project)
    else:
        # Raises 404 when the caller is neither owner nor collaborator, so an
        # unrelated project can never be overwritten through this upsert.
        project = get_project_for_user(project_id, user, session)

    project.name = body.name
    project.company_name = body.company_name
    project.pitch = body.pitch
    project.industry = body.industry
    project.business_model = body.business_model
    project.url = body.website_url
    project.targets = body.targets
    project.audience = body.audience
    project.competition = body.competition
    project.brand_channels = body.brand_channels
    project.updated_at = datetime.now(timezone.utc)
    session.add(project)
    if is_new:
        # Flush after the NOT NULL columns are populated, so the owner row can
        # reference a project that actually exists.
        session.flush()
        ensure_owner_membership(project, session)
    session.commit()
    session.refresh(project)
    return _to_out(
        project,
        role=member_role(project_id, user.id, session) or ROLE_OWNER,
        owner_email=_owner_emails([project], session).get(project.id, ""),
    )


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Owner-only. A collaborator who wants out leaves via
    DELETE /api/user/projects/{id}/members/me instead."""
    project = get_project_for_user(project_id, user, session, require_owner=True)
    session.delete(project)
    session.commit()
