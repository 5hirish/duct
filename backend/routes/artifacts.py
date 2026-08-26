"""Artifact library endpoints — /api/user/artifacts (Bearer JWT).

Read/serve/delete for the versioned artifact store (models/artifact.py).
Every route is membership-checked through service.membership — content bytes
are served only here, never from a public URL.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

from db.session import get_session
from models.artifact import Artifact
from models.auth import User
from service.artifact_store import delete_artifact_group, latest_versions
from service.auth import get_current_user
from service.membership import get_project_for_user
from service.storage import get_private_bytes

router = APIRouter(tags=["artifacts"])


def _serialize(row: Artifact, *, version_count: int | None = None) -> dict:
    out = {
        "id": str(row.id),
        "group_id": str(row.group_id),
        "version": row.version,
        "project_id": str(row.project_id),
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "agent_type": row.agent_type,
        "kind": row.kind,
        "content_type": row.content_type,
        "title": row.title,
        "filename": row.filename,
        "has_content": bool(row.storage_key),
        "size_bytes": row.size_bytes,
        "summary": row.summary,
        "meta": row.meta,
        "created_at": row.created_at.isoformat(),
    }
    if version_count is not None:
        out["version_count"] = version_count
    return out


def _get_readable(session: Session, user: User, artifact_id: UUID) -> Artifact:
    row = session.execute(select(Artifact).where(Artifact.id == artifact_id)).scalars().first()
    if row is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Artifact not found")
    # Membership gate — raises 404 for non-members (no existence leak).
    get_project_for_user(row.project_id, user, session)
    return row


@router.get("")
def list_artifacts(
    project_id: UUID,
    kind: str = "",
    agent_type: str = "",
    conversation_id: UUID | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Latest version per artifact group, newest first."""
    get_project_for_user(project_id, user, session)
    stmt = select(Artifact).where(Artifact.project_id == project_id)
    if kind:
        stmt = stmt.where(Artifact.kind == kind)
    if agent_type:
        stmt = stmt.where(Artifact.agent_type == agent_type)
    if conversation_id is not None:
        stmt = stmt.where(Artifact.conversation_id == conversation_id)
    rows = list(session.execute(stmt.order_by(Artifact.created_at.desc())).scalars())
    counts: dict[UUID, int] = {}
    for row in rows:
        counts[row.group_id] = counts.get(row.group_id, 0) + 1
    return [
        _serialize(row, version_count=counts[row.group_id])
        for row in latest_versions(rows)[: max(1, min(limit, 200))]
    ]


@router.get("/{artifact_id}")
def get_artifact(
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_readable(session, user, artifact_id)
    out = _serialize(row)
    out["structured_json"] = row.structured_json
    return out


@router.get("/{artifact_id}/versions")
def list_artifact_versions(
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    row = _get_readable(session, user, artifact_id)
    versions = list(
        session.execute(
            select(Artifact)
            .where(Artifact.group_id == row.group_id)
            .order_by(Artifact.version.desc())
        ).scalars()
    )
    return [_serialize(v) for v in versions]


def _content_response(row: Artifact, *, as_attachment: bool) -> Response:
    if not row.storage_key:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="This artifact has no stored file — render it from structured_json.",
        )
    data = get_private_bytes(row.storage_key)
    if data is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Artifact content unavailable")
    headers = {}
    if as_attachment:
        headers["Content-Disposition"] = f'attachment; filename="{row.filename or row.storage_key.rsplit("/", 1)[-1]}"'
    return Response(
        content=data,
        media_type=row.content_type or "application/octet-stream",
        headers=headers,
    )


@router.get("/{artifact_id}/content")
def get_artifact_content(
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    return _content_response(_get_readable(session, user, artifact_id), as_attachment=False)


@router.get("/{artifact_id}/download")
def download_artifact(
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    return _content_response(_get_readable(session, user, artifact_id), as_attachment=True)


@router.delete("/{artifact_id}", status_code=204)
def delete_artifact(
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Delete the whole artifact group (every version) the row belongs to."""
    row = _get_readable(session, user, artifact_id)
    delete_artifact_group(session, row.group_id)
