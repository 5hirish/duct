"""Agent context endpoints — GET/PUT /api/user/projects/{id}/context/{agent_id}."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

from agents.registry import AGENT_REGISTRY
from db.session import get_session
from models.agent_context import AgentContext
from models.auth import User
from models.project import Project
from service.auth import get_current_user

router = APIRouter(tags=["user-contexts"])


class ContextOut(BaseModel):
    project_id: UUID
    agent_id: str
    data: dict
    updated_at: str


def _assert_project_owned(project_id: UUID, user: User, session: Session) -> Project:
    project = session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    ).scalars().first()
    if project is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("/{project_id}/context/{agent_id}")
def get_context(
    project_id: UUID,
    agent_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ContextOut:
    if agent_id not in AGENT_REGISTRY:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Unknown agent: {agent_id!r}")
    _assert_project_owned(project_id, user, session)
    ctx = session.execute(
        select(AgentContext).where(
            AgentContext.project_id == project_id,
            AgentContext.agent_id == agent_id,
        )
    ).scalars().first()
    return ContextOut(
        project_id=project_id,
        agent_id=agent_id,
        data=ctx.data if ctx else {},
        updated_at=ctx.updated_at.isoformat() if ctx else "",
    )


@router.put("/{project_id}/context/{agent_id}")
def upsert_context(
    project_id: UUID,
    agent_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ContextOut:
    if agent_id not in AGENT_REGISTRY:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Unknown agent: {agent_id!r}")
    if len(json.dumps(body)) > 64_000:
        raise HTTPException(status_code=413, detail="Context payload too large.")
    _assert_project_owned(project_id, user, session)

    now = datetime.now(timezone.utc)
    ctx = session.execute(
        select(AgentContext).where(
            AgentContext.project_id == project_id,
            AgentContext.agent_id == agent_id,
        )
    ).scalars().first()

    if ctx is None:
        ctx = AgentContext(
            project_id=project_id,
            agent_id=agent_id,
            data=body,
            updated_at=now,
        )
    else:
        ctx.data = body
        ctx.updated_at = now

    session.add(ctx)
    session.commit()
    session.refresh(ctx)
    return ContextOut(
        project_id=project_id,
        agent_id=agent_id,
        data=ctx.data,
        updated_at=ctx.updated_at.isoformat(),
    )
