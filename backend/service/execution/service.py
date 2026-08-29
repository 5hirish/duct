"""Staged-execution core — propose / apply / rollback, HTTP-free.

Extracted from routes/execution.py so the HTTP routes and the agent-facing MCP
tools (agents/tools/execution_tools.py) share one implementation instead of
agents making HTTP round-trips to their own server. The route stays a thin
auth + credential-resolution shell.

Contract:
- ``propose_change_set`` previews and guardrail-checks every change, computes
  per-change auto-apply eligibility (service/execution/policy.py), persists the
  set, and — when the policy passes for an agent-sourced set on an
  ``assisted``-autonomy project — applies it inline with ``applied_by="auto"``.
- Validation failures raise ``ValueError`` (routes translate to 422); state
  conflicts raise ``StateError`` (routes translate to 409). Executor failures
  never raise — they are recorded per change.
"""

from __future__ import annotations


from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlmodel import Session

from models.execution import ExecutionChangeSet, ExecutionGuardrail
from models.project import Project
from service.activity import log_activity
from service.memory import record_change_set_memory
from service.execution.guardrails import violations_for
from service.execution.policy import change_auto_eligible, should_auto_apply
from service.execution.registry import get_executor
from utils.dates import utcnow


# Ops whose successful apply/rollback changes the LIVE site — each gets its own
# activity row (the deploy log) on top of the change-set transition row.
_GTM_PUBLISH_OPS = {"gtm.publish_version", "gtm.rollback_to_version"}


def log_change_set_transition(
    db, row: ExecutionChangeSet, action: str, *, source: str, summary: str, data: dict | None = None
) -> None:
    log_activity(
        db,
        category="execution",
        action=action,
        source=source,
        project_id=row.project_id,
        user_id=row.user_id,
        conversation_id=row.conversation_id,
        agent_type=row.agent_type,
        connector_type=row.connector_type,
        account_id=row.account_id,
        target_type="change_set",
        target_id=str(row.id),
        summary=summary,
        data=data,
    )


def _log_gtm_publishes(db, row: ExecutionChangeSet, changes: list[dict], *, source: str) -> None:
    """One deploy-log row per GTM publish that just happened (apply or rollback)."""
    for change in changes:
        if change.get("op_type") not in _GTM_PUBLISH_OPS:
            continue
        if change.get("status") == "applied":
            result = change.get("result") or {}
            published = str(result.get("published_version_id") or "")
            prior = str((result.get("rollback") or {}).get("prior_live_version_id") or "")
            log_change_set_transition(
                db,
                row,
                "gtm.published",
                source=source,
                summary=(
                    f"Published GTM container version {published or '?'}"
                    + (f" (prior live: {prior})" if prior else " (first publish)")
                ),
                data={"published_version_id": published, "prior_live_version_id": prior},
            )
        elif change.get("status") == "rolled_back":
            republished = str((change.get("rollback_result") or {}).get("republished_version_id") or "")
            log_change_set_transition(
                db,
                row,
                "gtm.published",
                source=source,
                summary=f"Republished prior GTM container version {republished or '?'} (rollback)",
                data={"published_version_id": republished, "rollback": True},
            )


class StateError(Exception):
    """The change set is not in a status that allows the requested transition."""


def guardrails_for(
    db: Session, user_id: UUID, connector_type: str, account_id: str
) -> list[ExecutionGuardrail]:
    rows = (
        db.execute(
            select(ExecutionGuardrail).where(
                ExecutionGuardrail.user_id == user_id,
                ExecutionGuardrail.connector_type == connector_type,
            )
        )
        .scalars()
        .all()
    )
    # Account-scoped rules apply to their account; blank account_id = whole connector.
    return [g for g in rows if not g.account_id or g.account_id == account_id]


def serialize_change_set(cs: ExecutionChangeSet) -> dict[str, Any]:
    return {
        "id": str(cs.id),
        "connector_type": cs.connector_type,
        "account_id": cs.account_id,
        "account_name": cs.account_name,
        "title": cs.title,
        "context": cs.context,
        "status": cs.status,
        "changes": cs.changes,
        "project_id": str(cs.project_id) if cs.project_id else None,
        "conversation_id": str(cs.conversation_id) if cs.conversation_id else None,
        "agent_type": cs.agent_type,
        "source": cs.source,
        "applied_by": cs.applied_by,
        "auto_apply_eligible": cs.auto_apply_eligible,
        "created_at": cs.created_at.isoformat(),
        "updated_at": cs.updated_at.isoformat(),
        "approved_at": cs.approved_at.isoformat() if cs.approved_at else None,
        "applied_at": cs.applied_at.isoformat() if cs.applied_at else None,
    }


def propose_change_set(
    db: Session,
    *,
    user_id: UUID,
    connector_type: str,
    account_id: str,
    account_name: str,
    title: str,
    context: str,
    changes: list[dict[str, Any]],
    creds: dict[str, str],
    project_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    source: str = "user",
) -> ExecutionChangeSet:
    """Preview + guardrail-check every change and persist the set.

    ``changes`` items carry {op_type, summary, target, payload}. When the
    autonomy policy passes (agent source + assisted project + every change
    eligible) the set is applied inline before returning.
    """
    if not changes:
        raise ValueError("A change set needs at least one change.")

    for change in changes:
        spec = get_executor(str(change.get("op_type") or ""))  # KeyError → caller
        if spec.connector_type != connector_type:
            raise ValueError(
                f"{spec.op_type} belongs to connector {spec.connector_type!r}, "
                f"not {connector_type!r}"
            )

    account_id = account_id.strip()
    guardrails = guardrails_for(db, user_id, connector_type, account_id)

    stored_changes: list[dict[str, Any]] = []
    for change in changes:
        record: dict[str, Any] = {
            "id": str(uuid4()),
            "op_type": change["op_type"],
            "summary": change.get("summary", ""),
            "target": change.get("target") or {},
            "payload": change.get("payload") or {},
            "status": "proposed",
        }
        spec = get_executor(record["op_type"])
        violations = violations_for(record, guardrails)
        if violations:
            record["status"] = "blocked"
            record["guardrail_violations"] = violations
        else:
            try:
                preview = spec.preview(record, creds)
                record["current"] = preview.pop("current", {})
                record["preview"] = preview
            except Exception as exc:  # noqa: BLE001 — any preview failure is recorded, never a 500
                record["preview"] = {"error": str(exc)}
        record["auto_eligible"] = change_auto_eligible(spec, record)
        stored_changes.append(record)

    project = db.get(Project, project_id) if project_id else None
    auto_eligible_set = all(c["auto_eligible"] for c in stored_changes)

    row = ExecutionChangeSet(
        user_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
        agent_type=agent_type,
        source=source,
        auto_apply_eligible=auto_eligible_set,
        connector_type=connector_type,
        account_id=account_id,
        account_name=account_name,
        title=title,
        context=context,
        changes=stored_changes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    blocked = sum(1 for c in stored_changes if c["status"] == "blocked")
    log_change_set_transition(
        db,
        row,
        "change_set.proposed",
        source=source,
        summary=(
            f"Proposed “{row.title}” — {len(stored_changes)} change(s) on {connector_type}"
            + (f", {blocked} blocked by guardrails" if blocked else "")
            + (" · eligible for auto-apply" if row.auto_apply_eligible else "")
        ),
        data={"change_count": len(stored_changes), "blocked": blocked},
    )

    if should_auto_apply(project, source, stored_changes):
        # Auto-approve then run the shared apply loop. Guardrails were checked
        # milliseconds ago in this same call; apply re-checks them anyway.
        approved = []
        for change in row.changes:
            change = dict(change)
            change["status"] = "approved"
            approved.append(change)
        row.changes = approved
        row.status = "approved"
        row.approved_at = utcnow()
        row.updated_at = utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        row = apply_change_set(db, row, creds, applied_by="auto")

    return row


def apply_change_set(
    db: Session,
    row: ExecutionChangeSet,
    creds: dict[str, str],
    *,
    applied_by: str = "user",
) -> ExecutionChangeSet:
    """Perform every approved change; record per-change results + rollback handles."""
    if row.status != "approved":
        raise StateError(
            f"Change set must be approved before applying (currently {row.status})."
        )

    guardrails = guardrails_for(db, row.user_id, row.connector_type, row.account_id)

    row.status = "applying"
    row.updated_at = utcnow()
    db.add(row)
    db.commit()

    applied = failed = 0
    updated = []
    newly_applied: list[dict[str, Any]] = []
    for change in row.changes:
        change = dict(change)
        if change["status"] != "approved":
            updated.append(change)
            continue

        # Defensive re-check: guardrails may have been added since proposal.
        violations = violations_for(change, guardrails)
        if violations:
            change["status"] = "blocked"
            change["guardrail_violations"] = violations
            updated.append(change)
            continue

        spec = get_executor(change["op_type"])
        try:
            change["result"] = spec.apply(change, creds)
            change["status"] = "applied"
            applied += 1
            newly_applied.append(change)
        except Exception as exc:  # noqa: BLE001 — record per-change, never lose results to a 500
            change["result"] = {"error": str(exc)}
            change["status"] = "failed"
            failed += 1
        updated.append(change)

    row.changes = updated
    row.applied_at = utcnow()
    row.updated_at = utcnow()
    row.status = "applied" if applied and not failed else ("partial" if applied else "failed")
    if applied:
        row.applied_by = applied_by
    db.add(row)
    db.commit()
    db.refresh(row)

    actor = "auto" if applied_by == "auto" else "user"
    action = {
        "applied": "change_set.auto_applied" if applied_by == "auto" else "change_set.applied",
        "partial": "change_set.partially_applied",
        "failed": "change_set.failed",
    }[row.status]
    log_change_set_transition(
        db,
        row,
        action,
        source=actor,
        summary=(
            f"{'Auto-applied' if applied_by == 'auto' else 'Applied'} “{row.title}” — "
            f"{applied} applied, {failed} failed"
        ),
        data={"applied": applied, "failed": failed, "applied_by": applied_by},
    )
    _log_gtm_publishes(db, row, newly_applied, source=actor)
    # What we actually did to the account becomes project memory, keyed on the
    # change set — a later rollback supersedes this entry rather than
    # contradicting it. Best-effort: never fails an apply that already ran.
    record_change_set_memory(db, row, applied=applied, failed=failed)
    return row


def rollback_change_set(
    db: Session, row: ExecutionChangeSet, creds: dict[str, str], *, actor: str = "user"
) -> ExecutionChangeSet:
    """Revert every applied change using its recorded rollback handle.

    ``actor`` is who initiated the rollback ("user" from the routes/UI,
    "agent" from the RollbackChangeSet MCP tool) — recorded in the activity log.
    """
    if row.status not in ("applied", "partial"):
        raise StateError(f"Nothing to roll back on a {row.status} change set.")

    reverted = errors = 0
    updated = []
    newly_rolled_back: list[dict[str, Any]] = []
    for change in row.changes:
        change = dict(change)
        if change["status"] != "applied":
            updated.append(change)
            continue
        spec = get_executor(change["op_type"])
        if spec.rollback is None:
            change.setdefault("result", {})["rollback_error"] = "This operation has no rollback."
            errors += 1
            updated.append(change)
            continue
        try:
            change["rollback_result"] = spec.rollback(change, creds)
            change["status"] = "rolled_back"
            reverted += 1
            newly_rolled_back.append(change)
        except Exception as exc:  # noqa: BLE001 — record per-change, never lose results to a 500
            change.setdefault("result", {})["rollback_error"] = str(exc)
            errors += 1
        updated.append(change)

    row.changes = updated
    row.updated_at = utcnow()
    if reverted and not errors:
        row.status = "rolled_back"
    db.add(row)
    db.commit()
    db.refresh(row)

    log_change_set_transition(
        db,
        row,
        "change_set.rolled_back" if reverted and not errors else "change_set.rollback_partial",
        source=actor,
        summary=f"Rolled back “{row.title}” — {reverted} reverted, {errors} error(s)",
        data={"reverted": reverted, "errors": errors},
    )
    _log_gtm_publishes(db, row, newly_rolled_back, source=actor)
    # Same state key as the apply entry above, so the digest shows "rolled back"
    # and the timeline keeps both rows with their validity ranges.
    record_change_set_memory(db, row, applied=reverted, failed=errors)
    return row
