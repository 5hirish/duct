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
from uuid import UUID

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
