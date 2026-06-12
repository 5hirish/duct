"""User project CRUD — GET/POST/PUT/DELETE /api/user/projects."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

from db.session import get_session
from models.auth import User
from models.project import Project
from service.auth import get_current_user

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


def _to_out(p: Project) -> ProjectOut:
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
    )


@router.get("")
def list_projects(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ProjectOut]:
    rows = session.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at)
    ).scalars().all()
    return [_to_out(r) for r in rows]


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
    session.commit()
    session.refresh(project)
    return _to_out(project)


@router.get("/{project_id}")
def get_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProjectOut:
    project = session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    ).scalars().first()
    if project is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return _to_out(project)


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
    """
    from datetime import datetime, timezone

    project = session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    ).scalars().first()
    if project is None:
        project = Project(id=project_id, user_id=user.id)
        session.add(project)

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
    session.commit()
    session.refresh(project)
    return _to_out(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    project = session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    ).scalars().first()
    if project is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    session.delete(project)
    session.commit()
