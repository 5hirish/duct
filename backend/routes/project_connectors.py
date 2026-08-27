"""Per-project connector bindings — /api/user/projects/{id}/connectors.

A binding points a project's connector type at ONE of the caller's stored
``connector_credentials`` rows, so different projects can use different
Stripe/ads accounts. Secrets are never duplicated: the binding references the
encrypted row, and deleting the credential cascades the binding away (the
project falls back to user-level resolution).

Trust model: reading/using/removing a binding requires project membership
(404 for non-members — never confirm a foreign project id). Creating one
additionally requires OWNING the referenced credential row: you can offer
your own accounts to a project, never point it at someone else's row —
though once bound, any member's agent runs use it (that is the point).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

from db.session import get_session
from models.auth import User
from models.connector import ConnectorCredential, ProjectConnector
from routes.user_connectors import ALLOWED_CONNECTOR_TYPES
from service.activity import log_activity
from service.auth import get_current_user
from service.membership import get_project_for_user
from utils.dates import utcnow

router = APIRouter(tags=["project-connectors"])


class BindingIn(BaseModel):
    connector_credential_id: UUID


def _serialize(binding: ProjectConnector, cred: ConnectorCredential | None) -> dict:
    return {
        "id": str(binding.id),
        "connector_type": binding.connector_type,
        "connector_credential_id": str(binding.connector_credential_id),
        "account_id": cred.account_id if cred else "",
        "account_name": cred.account_name if cred else "",
        "created_at": binding.created_at.isoformat(),
        "updated_at": binding.updated_at.isoformat(),
    }


@router.get("/{project_id}/connectors")
def list_bindings(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    get_project_for_user(project_id, user, session)
    rows = session.execute(
        select(ProjectConnector, ConnectorCredential)
        .join(
            ConnectorCredential,
            ConnectorCredential.id == ProjectConnector.connector_credential_id,
        )
        .where(ProjectConnector.project_id == project_id)
        .order_by(ProjectConnector.connector_type)
    ).all()
    return [_serialize(binding, cred) for binding, cred in rows]


@router.put("/{project_id}/connectors/{connector_type}")
def bind_connector(
    project_id: UUID,
    connector_type: str,
    body: BindingIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    get_project_for_user(project_id, user, session)
    if connector_type not in ALLOWED_CONNECTOR_TYPES:
        raise HTTPException(
            status_code=422, detail=f"Unknown connector type: {connector_type!r}"
        )

    # Ownership gate: 404 (not 403) so foreign credential ids stay unconfirmed.
    cred = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.id == body.connector_credential_id,
            ConnectorCredential.user_id == user.id,
        )
    ).scalars().first()
    if cred is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Credential not found")
    if cred.connector_type != connector_type:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Credential is for {cred.connector_type!r}, "
                f"not {connector_type!r}."
            ),
        )

    existing = session.execute(
        select(ProjectConnector).where(
            ProjectConnector.project_id == project_id,
            ProjectConnector.connector_type == connector_type,
        )
    ).scalars().first()

    if existing is not None:
        existing.connector_credential_id = cred.id
        existing.created_by_user_id = user.id
        existing.updated_at = utcnow()
        binding = existing
    else:
        binding = ProjectConnector(
            project_id=project_id,
            connector_type=connector_type,
            connector_credential_id=cred.id,
            created_by_user_id=user.id,
        )
    session.add(binding)
    session.commit()
    session.refresh(binding)
    log_activity(
        session,
        category="connector",
        action="project_connector.bound",
        source="user",
        project_id=project_id,
        user_id=user.id,
        connector_type=connector_type,
        account_id=cred.account_id,
        target_type="project_connector",
        target_id=str(binding.id),
        summary=(
            f"Mapped {connector_type} to "
            f"{cred.account_name or cred.account_id or 'the saved account'} for this project"
        ),
    )
    return _serialize(binding, cred)


@router.delete("/{project_id}/connectors/{connector_type}", status_code=204)
def unbind_connector(
    project_id: UUID,
    connector_type: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    get_project_for_user(project_id, user, session)
    binding = session.execute(
        select(ProjectConnector).where(
            ProjectConnector.project_id == project_id,
            ProjectConnector.connector_type == connector_type,
        )
    ).scalars().first()
    if binding is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No binding for this connector")
    session.delete(binding)
    session.commit()
    log_activity(
        session,
        category="connector",
        action="project_connector.unbound",
        source="user",
        project_id=project_id,
        user_id=user.id,
        connector_type=connector_type,
        target_type="project_connector",
        target_id=str(binding.id),
        summary=f"Removed the project's {connector_type} mapping",
    )
