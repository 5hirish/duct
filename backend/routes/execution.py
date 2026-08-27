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


from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

# Imported for their register_executor side effects.
import service.execution.ga4_exec  # noqa: F401
import service.execution.google_ads_exec  # noqa: F401
import service.execution.gtm_exec  # noqa: F401
from db.session import get_session
from models.auth import User
from models.execution import ExecutionChangeSet, ExecutionGuardrail
from service.auth import get_current_user
from service.execution.creds import resolve_execution_creds
from service.execution.registry import EXECUTOR_REGISTRY
from service.execution.service import (
    StateError,
    apply_change_set as apply_core,
    log_change_set_transition,
    propose_change_set as propose_core,
    rollback_change_set as rollback_core,
    serialize_change_set as _serialize,
)
from service.membership import get_project_for_user
from utils.dates import utcnow

router = APIRouter(tags=["execution"])


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
    # Optional provenance: ties the set to a project the caller belongs to.
    # Browser proposals are always source="user" and never auto-apply.
    project_id: UUID | None = None


class ApproveIn(BaseModel):
    change_ids: list[str] | None = None  # None = approve everything not blocked


class ExecuteIn(BaseModel):
    credentials: CredentialsIn = Field(default_factory=CredentialsIn)


class GuardrailIn(BaseModel):
    connector_type: str
    account_id: str = ""
    rule: str
    match: dict = Field(default_factory=dict)


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
    if body.project_id is not None:
        # 404 for non-members — never confirm a foreign project id exists.
        get_project_for_user(body.project_id, user, session)

    creds = resolve_execution_creds(
        session,
        user.id,
        body.connector_type,
        body.account_id,
        override=body.credentials.model_dump(),
    )
    try:
        row = propose_core(
            session,
            user_id=user.id,
            connector_type=body.connector_type,
            account_id=body.account_id,
            account_name=body.account_name,
            title=body.title,
            context=body.context,
            changes=[c.model_dump() for c in body.changes],
            creds=creds,
            project_id=body.project_id,
            source="user",
        )
    except (KeyError, ValueError) as exc:
        detail = str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)
        raise HTTPException(status_code=422, detail=detail) from exc
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
    row.approved_at = utcnow()
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    approved_count = sum(1 for c in row.changes if c["status"] == "approved")
    log_change_set_transition(
        session,
        row,
        "change_set.approved",
        source="user",
        summary=f"Approved “{row.title}” — {approved_count} change(s)",
        data={"approved": approved_count, "subset": body.change_ids is not None},
    )
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
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    log_change_set_transition(
        session,
        row,
        "change_set.rejected",
        source="user",
        summary=f"Rejected “{row.title}”",
    )
    return _serialize(row)


@router.post("/{change_set_id}/apply")
def apply_change_set(
    change_set_id: UUID,
    body: ExecuteIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_owned(session, user, change_set_id)
    creds = resolve_execution_creds(
        session,
        user.id,
        row.connector_type,
        row.account_id,
        override=body.credentials.model_dump(),
    )
    try:
        row = apply_core(session, row, creds, applied_by="user")
    except StateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize(row)


@router.post("/{change_set_id}/rollback")
def rollback_change_set(
    change_set_id: UUID,
    body: ExecuteIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_owned(session, user, change_set_id)
    creds = resolve_execution_creds(
        session,
        user.id,
        row.connector_type,
        row.account_id,
        override=body.credentials.model_dump(),
    )
    try:
        row = rollback_core(session, row, creds)
    except StateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize(row)
