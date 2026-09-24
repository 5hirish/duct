"""Best-effort activity logging — must never break the write it records.

``log_activity`` appends one transition row using the caller's session. Every
call site sits immediately after the domain write's own commit, so the extra
commit here is a safe point; any failure is swallowed (logged + rolled back)
because an audit-trail miss must never fail an apply, a rollback, or an
artifact write.

Call sites (wave 1): service/execution/service.py (every change-set lifecycle
transition + GTM publishes), routes/execution.py (human approve/reject), and
service/artifact_store.py::persist_artifact_version (every artifact version).
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from models.activity import ActivityLog

logger = logging.getLogger(__name__)


def log_activity(
    db,
    *,
    category: str,
    action: str,
    source: str = "user",
    project_id: UUID | None = None,
    user_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    connector_type: str = "",
    account_id: str = "",
    target_type: str = "",
    target_id: str = "",
    summary: str = "",
    data: dict | None = None,
) -> None:
    """Append one activity row. Swallows every failure."""
    try:
        row = ActivityLog(
            category=category,
            action=action,
            source=source,
            project_id=project_id,
            user_id=user_id,
            conversation_id=conversation_id,
            agent_type=agent_type,
            connector_type=connector_type,
            account_id=account_id,
            target_type=target_type,
            target_id=str(target_id) if target_id else "",
            summary=summary,
            data=data or {},
        )
        db.add(row)
        db.commit()
    except Exception:  # noqa: BLE001 — the audit trail never breaks the write it records
        logger.warning("activity: failed to record %s/%s", category, action, exc_info=True)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


# How many decisions one turn restates. A person clears a queue of cards in one
# sitting at most; past this the agent reads the change sets themselves.
_DECISION_LIMIT = 20


def user_decisions_since(db, conversation_id: UUID, since: datetime | None) -> list[ActivityLog]:
    """What a person did to this conversation's change sets after ``since``.

    The agent that proposed a set is told to wait for the review card and not
    to poll, so an approve, reject, apply or rollback made on the card never
    reaches it: this log is the only place those clicks are written down.
    Agent- and auto-sourced rows are left out, since the agent saw those happen.
    """
    stmt = select(ActivityLog).where(
        ActivityLog.conversation_id == conversation_id,
        ActivityLog.category == "execution",
        ActivityLog.source == "user",
        ActivityLog.action.startswith("change_set."),
    )
    if since is not None:
        stmt = stmt.where(ActivityLog.created_at > since)
    stmt = stmt.order_by(ActivityLog.created_at).limit(_DECISION_LIMIT)
    try:
        return list(db.execute(stmt).scalars().all())
    except Exception:  # noqa: BLE001 — a missing reminder must never block a message
        logger.warning("activity: could not read decisions for %s", conversation_id, exc_info=True)
        return []
