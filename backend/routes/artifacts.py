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
        "slug": row.slug,
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


@router.get("/resolve")
def resolve_artifact(
    project_id: UUID,
    ref: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Resolve a slug / group id / version id / pasted app URL to the latest
    version — the cross-session addressing contract."""
    get_project_for_user(project_id, user, session)
    from service.artifact_store import resolve_reference

    row = resolve_reference(session, project_id, ref)
    if row is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Artifact not found")
    return _serialize(row)


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


@router.post("/{artifact_id}/restore", status_code=201)
def restore_artifact_version(
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Promote this snapshot to a NEW head version (history is never rewritten)."""
    row = _get_readable(session, user, artifact_id)
    from service.artifact_store import restore_version

    new_head = restore_version(session, row, user_id=user.id)
    return _serialize(new_head)


@router.get("/{artifact_id}/diff")
def diff_artifact_version(
    artifact_id: UUID,
    against: str = "prev",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """'Show changes': unified diff of this version against another (default:
    the previous version). Adds a semantic summary for structured reports."""
    import difflib

    from sqlalchemy import select as _select

    from service.artifact_store import DUCT_REPORT_JSON, artifact_text_content

    row = _get_readable(session, user, artifact_id)
    if against == "prev":
        base = (
            session.execute(
                _select(Artifact)
                .where(Artifact.group_id == row.group_id, Artifact.version < row.version)
                .order_by(Artifact.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
    else:
        base = _get_readable(session, user, UUID(against))
        if base.group_id != row.group_id:
            raise HTTPException(status_code=422, detail="Versions belong to different artifacts")
    if base is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No earlier version to diff against")

    base_text = artifact_text_content(base)
    target_text = artifact_text_content(row)
    diff_text = "\n".join(
        difflib.unified_diff(
            base_text.splitlines(),
            target_text.splitlines(),
            fromfile=f"v{base.version}",
            tofile=f"v{row.version}",
            lineterm="",
            n=3,
        )
    )

    out: dict = {
        "base_version": base.version,
        "target_version": row.version,
        "diff": diff_text,
    }
    # Semantic diff for structured reports — where JSON beats HTML.
    if row.content_type in (DUCT_REPORT_JSON, "application/json") and row.kind == "report":
        try:
            def _findings(r):
                sd = (r.structured_json or {}).get("structured_data") or {}
                return {
                    f.get("title", "")
                    for c in sd.get("categories", [])
                    for f in c.get("findings", [])
                }, sd.get("overall_score")

            base_f, base_score = _findings(base)
            target_f, target_score = _findings(row)
            out["summary"] = {
                "score_before": base_score,
                "score_after": target_score,
                "new_findings": sorted(target_f - base_f),
                "resolved_findings": sorted(base_f - target_f),
            }
        except Exception:  # noqa: BLE001 — summary is best-effort sugar
            pass
    return out


_EXPORT_FORMATS = {"pdf", "csv", "md"}


@router.get("/{artifact_id}/export")
def export_artifact(
    artifact_id: UUID,
    format: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """Derived export of one version, generated on demand and cached in object
    storage keyed by (version, format)."""
    from service.artifact_store import (
        DUCT_REPORT_JSON,
        DUCT_TABLE_JSON,
        artifact_text_content,
    )
    from service.storage import get_private_bytes as _get_bytes
    from service.storage import put_private as _put_bytes

    fmt = format.lower().strip()
    if fmt not in _EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail=f"format must be one of {sorted(_EXPORT_FORMATS)}")
    row = _get_readable(session, user, artifact_id)

    cache_key = f"projects/{row.project_id}/artifacts/{row.group_id}/exports/v{row.version}.{fmt}"
    media = {"pdf": "application/pdf", "csv": "text/csv", "md": "text/markdown"}[fmt]
    stem = (row.filename or "artifact").rsplit(".", 1)[0]
    headers = {"Content-Disposition": f'attachment; filename="{stem}.{fmt}"'}

    cached = _get_bytes(cache_key)
    if cached is not None:
        return Response(content=cached, media_type=media, headers=headers)

    if fmt == "pdf":
        if row.kind != "report" or row.content_type not in (DUCT_REPORT_JSON, "application/json"):
            raise HTTPException(status_code=422, detail="PDF export is available for structured reports only")
        from service.report_pdf import generate_report_pdf

        data = generate_report_pdf(row.structured_json)
    elif fmt == "csv":
        if row.content_type == "text/csv":
            data = artifact_text_content(row).encode("utf-8")
        elif row.content_type == DUCT_TABLE_JSON:
            import csv as _csv
            import io
            import json as _json

            table = _json.loads(artifact_text_content(row) or "{}")
            buf = io.StringIO()
            writer = _csv.writer(buf)
            writer.writerow(table.get("columns", []))
            writer.writerows(table.get("rows", []))
            data = buf.getvalue().encode("utf-8")
        else:
            raise HTTPException(status_code=422, detail="CSV export is available for datasets only")
    else:  # md
        if row.content_type != "text/markdown":
            raise HTTPException(status_code=422, detail="Markdown export is available for markdown artifacts only")
        data = artifact_text_content(row).encode("utf-8")

    try:
        _put_bytes(cache_key, data, media)
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    return Response(content=data, media_type=media, headers=headers)


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
