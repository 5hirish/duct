"""User project CRUD — GET/POST/PUT/DELETE /api/user/projects."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlmodel import Session

from db.session import get_session
from models.auth import User
from models.execution import (
    AUTONOMY_ASK,
    AUTONOMY_LEVELS,
    is_writable_autonomy,
    normalize_autonomy,
)
from models.membership import ROLE_COLLABORATOR, ROLE_OWNER
from models.project import Project, unique_slug
from service.auth import get_current_user
from service.membership import accessible_projects, get_project_for_user, member_role
from service.project_draft import (
    DRAFT_SOURCES,
    FIELDS,
    clean_labels,
    reconcile_save,
    snapshot,
)
from service.project_writes import apply_draft, finish_write, project_for_write
from utils.dates import utcnow

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
    # Where each drafted field came from, as the client last knew it. Absent
    # (None) from a client that predates the server keeping labels, which
    # service/project_draft.reconcile_save treats as last write wins. Loosely
    # typed on purpose: a label this build does not know is dropped by
    # clean_labels, where a strict type would 422 the person's whole save.
    provenance: dict[str, Any] | None = None

    @field_validator("targets", "audience", "competition", "brand_channels", mode="after")
    @classmethod
    def _check_size(cls, v: dict) -> dict:
        if len(json.dumps(v)) > _JSONB_MAX_BYTES:
            raise ValueError("Section payload too large (max 128 KB).")
        return v


class DraftFieldIn(BaseModel):
    value: Any = None
    provenance: str

    @field_validator("provenance")
    @classmethod
    def _a_draft_source(cls, v: str) -> str:
        if v not in DRAFT_SOURCES:
            raise ValueError(f"provenance must be one of {sorted(DRAFT_SOURCES)}")
        return v


class ProjectDraftIn(BaseModel):
    """A PROJECT_DRAFT event's fields: ``{name: {value, provenance}}``."""

    fields: dict[str, DraftFieldIn]

    @field_validator("fields", mode="after")
    @classmethod
    def _check_fields(cls, v: dict[str, DraftFieldIn]) -> dict[str, DraftFieldIn]:
        if len(json.dumps({k: f.value for k, f in v.items()}, default=str)) > _JSONB_MAX_BYTES:
            raise ValueError("Draft payload too large (max 128 KB).")
        for name, field in v.items():
            spec = FIELDS.get(name)
            if spec and field.value is not None and not isinstance(field.value, spec.kind):
                raise ValueError(f"{name} must be a {spec.kind.__name__}")
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
    # Always one of AUTONOMY_LEVELS — legacy "manual" is normalized on the way
    # out, so no client ever has to know the alias exists.
    autonomy_level: str = AUTONOMY_ASK
    created_at: str
    updated_at: str
    # Caller's relationship to this project. The app uses it to label shared
    # projects and to hide owner-only controls (invite, remove, delete).
    role: str = ROLE_OWNER
    owner_email: str = ""
    # Where each drafted field came from ("user", "crawl", "document",
    # "inferred"). The app renders a chip from it and merges by it.
    provenance: dict = {}


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
        autonomy_level=normalize_autonomy(p.autonomy_level),
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
        role=role,
        owner_email=owner_email,
        provenance=p.provenance or {},
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
        slug=unique_slug(session, user.id, body.name),
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
    reconcile_save(project, snapshot(None), {}, clean_labels(body.provenance))
    # The targets and competitors typed into onboarding become dated project
    # memory, so agents cite the operator's own numbers instead of re-asking.
    project = finish_write(project, True, user, session)
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


def _out(project: Project, user: User, session: Session) -> ProjectOut:
    return _to_out(
        project,
        role=member_role(project.id, user.id, session) or ROLE_OWNER,
        owner_email=_owner_emails([project], session).get(project.id, ""),
    )


@router.put("/{project_id}")
def update_project(
    project_id: UUID,
    body: ProjectIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProjectOut:
    """Upsert by client-supplied id: the person saving their project.

    Collaborators may edit an existing project; the create branch only runs for
    ids that belong to nobody, and the caller becomes its owner. The save
    replaces every section, then ``reconcile_save`` puts back each drafted
    field the client only carried along: an older copy of a draft must not
    undo the newer one the server holds.
    """
    project, is_new = project_for_write(project_id, user, session, name=body.name)
    before = snapshot(None if is_new else project)
    before_labels = {} if is_new else dict(project.provenance or {})

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
    reconcile_save(project, before, before_labels, clean_labels(body.provenance))
    project.updated_at = utcnow()
    return _out(finish_write(project, is_new, user, session), user, session)


@router.post("/{project_id}/draft")
def draft_project(
    project_id: UUID,
    body: ProjectDraftIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProjectOut:
    """Merge a draft into the project, under the rules in service/project_draft.py.

    Creates the project when its id belongs to nobody, like the PUT, because
    onboarding drafts a project the browser made a moment ago. The MCP
    server's ``draft_project`` tool writes through the same function.
    """
    project, _, _ = apply_draft(
        project_id, {key: field.model_dump() for key, field in body.fields.items()}, user, session
    )
    return _out(project, user, session)


class ProjectSettingsIn(BaseModel):
    autonomy_level: str


@router.patch("/{project_id}")
def patch_project_settings(
    project_id: UUID,
    body: ProjectSettingsIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProjectOut:
    """Owner-only safety settings. Autonomy governs how freely the agent asks,
    and whether reversible, guardrail-clean, non-destructive agent-proposed
    change sets may apply without an approval click: 'ask' (nothing applies),
    'assisted' or 'auto' (the same allowlist — `auto` reduces interruption, not
    oversight). Destructive ops always wait regardless, at every level — see
    service/execution/policy.py.

    "manual" is accepted as the legacy spelling of "ask" so an older client
    keeps working; anything else unrecognised is a 422 rather than a silent
    downgrade, because quietly storing a level the caller did not ask for is
    how a project ends up more or less autonomous than its owner believes."""
    from fastapi import HTTPException

    project = get_project_for_user(project_id, user, session, require_owner=True)
    if not is_writable_autonomy(body.autonomy_level):
        raise HTTPException(
            status_code=422,
            detail=f"autonomy_level must be one of {sorted(AUTONOMY_LEVELS)}",
        )
    project.autonomy_level = normalize_autonomy(body.autonomy_level)
    project.updated_at = utcnow()
    session.add(project)
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
