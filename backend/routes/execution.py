"""Staged-execution endpoints — /api/execute.

Two-phase commit over connector mutations:
  POST /api/execute            propose a change set (each change previewed +
                               guardrail-checked; violations arrive blocked)
  POST /api/execute/{id}/approve   human approval (all or a subset)
  POST /api/execute/{id}/apply     perform approved changes, record results +
                                   rollback handles
  POST /api/execute/{id}/rollback  revert applied changes
  POST /api/execute/{id}/reject    discard without applying

Credentials resolve per request: BYO fields in the body win, then the user's
stored (Fernet-encrypted) connector credentials, then server env fallbacks —
see ``service/execution/creds.py``. Nothing from the body is persisted here.
Guardrails are per-account invariants enforced in code at both preview and
apply time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

# Imported for their register_executor side effects.
import service.execution.ga4_exec  # noqa: F401
import service.execution.google_ads_exec  # noqa: F401
from db.session import get_session
from models.auth import User
from models.execution import ExecutionChangeSet, ExecutionGuardrail
from service.auth import get_current_user
from service.execution.creds import resolve_execution_creds
from service.execution.guardrails import violations_for
from service.execution.registry import EXECUTOR_REGISTRY, get_executor

router = APIRouter(tags=["execution"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CredentialsIn(BaseModel):
    refresh_token: str = ""
    developer_token: str = ""  # BYO Google Ads API access
    login_customer_id: str = ""


class ChangeIn(BaseModel):
    op_type: str
    summary: str = ""
    target: dict = Field(default_factory=dict)
    payload: dict = Field(default_factory=dict)


class ChangeSetIn(BaseModel):
    connector_type: str
    account_id: str = ""
    account_name: str = ""
    title: str
    context: str = ""
    changes: list[ChangeIn]
    credentials: CredentialsIn = Field(default_factory=CredentialsIn)


class ApproveIn(BaseModel):
    change_ids: list[str] | None = None  # None = approve everything not blocked


class ExecuteIn(BaseModel):
    credentials: CredentialsIn = Field(default_factory=CredentialsIn)


class GuardrailIn(BaseModel):
    connector_type: str
    account_id: str = ""
    rule: str
    match: dict = Field(default_factory=dict)


def _guardrails_for(
    session: Session, user_id: UUID, connector_type: str, account_id: str
) -> list[ExecutionGuardrail]:
    rows = (
        session.execute(
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


def _serialize(cs: ExecutionChangeSet) -> dict[str, Any]:
    return {
        "id": str(cs.id),
        "connector_type": cs.connector_type,
        "account_id": cs.account_id,
        "account_name": cs.account_name,
        "title": cs.title,
        "context": cs.context,
        "status": cs.status,
        "changes": cs.changes,
        "created_at": cs.created_at.isoformat(),
        "updated_at": cs.updated_at.isoformat(),
        "approved_at": cs.approved_at.isoformat() if cs.approved_at else None,
        "applied_at": cs.applied_at.isoformat() if cs.applied_at else None,
    }


def _get_owned(session: Session, user: User, change_set_id: UUID) -> ExecutionChangeSet:
    row = (
        session.execute(
            select(ExecutionChangeSet).where(
                ExecutionChangeSet.id == change_set_id,
                ExecutionChangeSet.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Change set not found")
    return row


# ---------------------------------------------------------------------------
# Guardrails (declared before /{change_set_id} routes)
# ---------------------------------------------------------------------------

@router.get("/guardrails")
def list_guardrails(
    connector_type: str = "",
    account_id: str = "",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(ExecutionGuardrail).where(ExecutionGuardrail.user_id == user.id)
    if connector_type:
        query = query.where(ExecutionGuardrail.connector_type == connector_type)
    rows = session.execute(query.order_by(ExecutionGuardrail.created_at)).scalars().all()
    if account_id:
        rows = [g for g in rows if not g.account_id or g.account_id == account_id]
    return [
        {
            "id": str(g.id),
            "connector_type": g.connector_type,
            "account_id": g.account_id,
            "rule": g.rule,
            "match": g.match,
            "active": g.active,
            "created_at": g.created_at.isoformat(),
        }
        for g in rows
    ]


@router.post("/guardrails", status_code=201)
def create_guardrail(
    body: GuardrailIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if not body.rule.strip():
        raise HTTPException(status_code=422, detail="rule is required")
    row = ExecutionGuardrail(
        user_id=user.id,
        connector_type=body.connector_type,
        account_id=body.account_id.strip(),
        rule=body.rule.strip(),
        match=body.match,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"id": str(row.id)}


@router.delete("/guardrails/{guardrail_id}", status_code=204)
def delete_guardrail(
    guardrail_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    row = (
        session.execute(
            select(ExecutionGuardrail).where(
                ExecutionGuardrail.id == guardrail_id,
                ExecutionGuardrail.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Guardrail not found")
    session.delete(row)
    session.commit()


# ---------------------------------------------------------------------------
# Change sets
# ---------------------------------------------------------------------------

@router.get("/ops")
def list_op_types() -> list[dict]:
    """Available executors (for agents/UI building proposals)."""
    return [
        {
            "op_type": spec.op_type,
            "connector_type": spec.connector_type,
            "label": spec.label,
            "destructive": spec.destructive,
            "supports_rollback": spec.rollback is not None,
        }
        for spec in EXECUTOR_REGISTRY.values()
    ]


@router.post("", status_code=201)
def propose_change_set(
    body: ChangeSetIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if not body.changes:
        raise HTTPException(status_code=422, detail="A change set needs at least one change.")

    for change in body.changes:
        try:
            spec = get_executor(change.op_type)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if spec.connector_type != body.connector_type:
            raise HTTPException(
                status_code=422,
                detail=f"{change.op_type} belongs to connector {spec.connector_type!r}, "
                f"not {body.connector_type!r}",
            )

    creds = resolve_execution_creds(
        session,
        user.id,
        body.connector_type,
        body.account_id,
        override=body.credentials.model_dump(),
    )
    guardrails = _guardrails_for(session, user.id, body.connector_type, body.account_id.strip())

    stored_changes: list[dict[str, Any]] = []
    for change in body.changes:
        record: dict[str, Any] = {
            "id": str(uuid4()),
            "op_type": change.op_type,
            "summary": change.summary,
            "target": change.target,
            "payload": change.payload,
            "status": "proposed",
        }
        violations = violations_for(record, guardrails)
        if violations:
            record["status"] = "blocked"
            record["guardrail_violations"] = violations
        else:
            spec = get_executor(change.op_type)
            try:
                preview = spec.preview(record, creds)
                record["current"] = preview.pop("current", {})
                record["preview"] = preview
            except Exception as exc:  # noqa: BLE001 — any preview failure is recorded, never a 500
                record["preview"] = {"error": str(exc)}
        stored_changes.append(record)

    row = ExecutionChangeSet(
        user_id=user.id,
        connector_type=body.connector_type,
        account_id=body.account_id.strip(),
        account_name=body.account_name,
        title=body.title,
        context=body.context,
        changes=stored_changes,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _serialize(row)


@router.get("")
def list_change_sets(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = (
        session.execute(
            select(ExecutionChangeSet)
            .where(ExecutionChangeSet.user_id == user.id)
            .order_by(ExecutionChangeSet.created_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return [_serialize(r) for r in rows]


@router.get("/{change_set_id}")
def get_change_set(
    change_set_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    return _serialize(_get_owned(session, user, change_set_id))


@router.post("/{change_set_id}/approve")
def approve_change_set(
    change_set_id: UUID,
    body: ApproveIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_owned(session, user, change_set_id)
    if row.status not in ("proposed", "approved"):
        raise HTTPException(status_code=409, detail=f"Cannot approve a {row.status} change set.")

    wanted = set(body.change_ids) if body.change_ids else None
    approved_any = False
    updated = []
    for change in row.changes:
        change = dict(change)
        if change["status"] in ("proposed", "approved") and (wanted is None or change["id"] in wanted):
            if change.get("preview", {}).get("error"):
                updated.append(change)
                continue  # a change whose preview failed cannot be approved
            change["status"] = "approved"
            approved_any = True
        updated.append(change)

    if not approved_any and not any(c["status"] == "approved" for c in updated):
        raise HTTPException(status_code=422, detail="Nothing approvable in this change set.")

    row.changes = updated
    row.status = "approved"
    row.approved_at = _utcnow()
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _serialize(row)


@router.post("/{change_set_id}/reject")
def reject_change_set(
    change_set_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_owned(session, user, change_set_id)
    if row.status in ("applied", "partial", "rolled_back"):
        raise HTTPException(status_code=409, detail=f"Cannot reject a {row.status} change set.")
    row.status = "rejected"
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _serialize(row)


@router.post("/{change_set_id}/apply")
def apply_change_set(
    change_set_id: UUID,
    body: ExecuteIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_owned(session, user, change_set_id)
    if row.status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"Change set must be approved before applying (currently {row.status}).",
        )

    creds = resolve_execution_creds(
        session,
        user.id,
        row.connector_type,
        row.account_id,
        override=body.credentials.model_dump(),
    )
    guardrails = _guardrails_for(session, user.id, row.connector_type, row.account_id)

    row.status = "applying"
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()

    applied = failed = 0
    updated = []
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
        except Exception as exc:  # noqa: BLE001 — record per-change, never lose results to a 500
            change["result"] = {"error": str(exc)}
            change["status"] = "failed"
            failed += 1
        updated.append(change)

    row.changes = updated
    row.applied_at = _utcnow()
    row.updated_at = _utcnow()
    row.status = "applied" if applied and not failed else ("partial" if applied else "failed")
    session.add(row)
    session.commit()
    session.refresh(row)
    return _serialize(row)


@router.post("/{change_set_id}/rollback")
def rollback_change_set(
    change_set_id: UUID,
    body: ExecuteIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_owned(session, user, change_set_id)
    if row.status not in ("applied", "partial"):
        raise HTTPException(status_code=409, detail=f"Nothing to roll back on a {row.status} change set.")

    creds = resolve_execution_creds(
        session,
        user.id,
        row.connector_type,
        row.account_id,
        override=body.credentials.model_dump(),
    )

    reverted = errors = 0
    updated = []
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
        except Exception as exc:  # noqa: BLE001 — record per-change, never lose results to a 500
            change.setdefault("result", {})["rollback_error"] = str(exc)
            errors += 1
        updated.append(change)

    row.changes = updated
    row.updated_at = _utcnow()
    if reverted and not errors:
        row.status = "rolled_back"
    session.add(row)
    session.commit()
    session.refresh(row)
    return _serialize(row)
