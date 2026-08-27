"""Activity feed — GET /api/user/activity.

Project-scoped, membership-checked timeline over ``activity_logs``: change-set
transitions, GTM publishes, artifact versions — each one row with actor
attribution. Filterable down to a single conversation so an audit chat's
proposals, auto-applies, rollbacks, and artifact versions read as one
timeline. Keyset-paginated on ``created_at`` (``before``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlmodel import Session

from db.session import get_session
from models.activity import ActivityLog
from models.auth import User
from service.auth import get_current_user
from service.membership import get_project_for_user
from utils.dates import parse_iso

router = APIRouter(tags=["activity"])

_MAX_LIMIT = 100


def _serialize(row: ActivityLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "category": row.category,
        "action": row.action,
        "source": row.source,
        "summary": row.summary,
        "agent_type": row.agent_type,
        "connector_type": row.connector_type,
        "account_id": row.account_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "data": row.data or {},
        "created_at": row.created_at.isoformat(),
    }


@router.get("")
def list_activity(
    project_id: UUID,
    conversation_id: UUID | None = None,
    category: str = "",
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    before: str = "",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    # 404 for non-members — never confirm a foreign project id exists.
    get_project_for_user(project_id, user, session)

    stmt = select(ActivityLog).where(ActivityLog.project_id == project_id)
    if conversation_id is not None:
        stmt = stmt.where(ActivityLog.conversation_id == conversation_id)
    if category:
        stmt = stmt.where(ActivityLog.category == category)
    if before:
        # created_at is timezone-aware, so the cursor has to be too — parse_iso
        # assumes UTC for a bare timestamp rather than letting the DB guess.
        cutoff = parse_iso(before)
        if cutoff is None:
            raise HTTPException(status_code=422, detail="before must be an ISO datetime")
        stmt = stmt.where(ActivityLog.created_at < cutoff)

    rows = (
        session.execute(stmt.order_by(ActivityLog.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    return {
        "items": [_serialize(r) for r in rows],
        # Keyset cursor: pass back as ?before= to fetch the next (older) page.
        "next_before": rows[-1].created_at.isoformat() if len(rows) == limit else None,
    }
