"""Credential resolution for staged execution.

Per-field priority: request override (browser BYO — unchanged behavior) →
project connector binding (``project_connectors``) → stored
``connector_credentials`` row (Fernet-encrypted, saved from the Connections
page) → server env fallback.

Stored rows are what make *agent-initiated* execution possible: an agent
running server-side has no browser session to hand it a refresh token.
Project bindings decide WHICH of a user's accounts a project uses (project A
bills through Stripe account X, project B through Y). A bound credential may
belong to a different project member than the caller — deliberately: the
project's account is the project's account. Every call site passing
``project_id`` is membership-gated (routes check ``get_project_for_user``;
MCP tools receive the id from a membership-checked session), so the binding
never widens access beyond the project. User-level lookups try the exact
(user, connector_type, account_id) row first, then the account-agnostic
(user, connector_type, "") row.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from config import get_configs
from models.connector import ConnectorCredential, ProjectConnector
from service.credentials import decrypt_credentials

logger = logging.getLogger(__name__)


def bound_credential_row(
    session: Session, project_id: UUID, connector_type: str
) -> ConnectorCredential | None:
    """The credential row a project has bound for one connector type, or None."""
    return (
        session.execute(
            select(ConnectorCredential)
            .join(
                ProjectConnector,
                ProjectConnector.connector_credential_id == ConnectorCredential.id,
            )
            .where(
                ProjectConnector.project_id == project_id,
                ProjectConnector.connector_type == connector_type,
            )
        )
        .scalars()
        .first()
    )


def _decrypt_row(row: ConnectorCredential) -> dict:
    try:
        data = decrypt_credentials(row.credentials_enc)
    except Exception as exc:  # noqa: BLE001 — stored creds are optional, never fatal
        logger.warning(
            "Could not decrypt stored %s credentials (row %s): %s",
            row.connector_type,
            row.id,
            exc,
        )
        return {}
    return data if isinstance(data, dict) else {}


def _stored_credentials(
    session: Session,
    user_id: UUID,
    connector_type: str,
    account_id: str,
    project_id: UUID | None = None,
) -> dict:
    """Best-effort decrypt of the credentials for a connector.

    Project binding first (when ``project_id`` is given), then the caller's
    own rows. Never raises: a missing row, a missing
    CREDENTIALS_ENCRYPTION_KEY, or a corrupt token all degrade to ``{}`` so
    the env fallback still applies.
    """
    if project_id is not None:
        bound = bound_credential_row(session, project_id, connector_type)
        # An explicitly-targeted different account skips the binding: the
        # caller asked for account Y, the project is bound to account X — the
        # caller's own rows for Y are the honest source, not X's secrets.
        if bound is not None and not (
            account_id and bound.account_id and bound.account_id != account_id
        ):
            data = _decrypt_row(bound)
            if data:
                return data
    account_ids = [account_id] if account_id else []
    if "" not in account_ids:
        account_ids.append("")
    for acct in account_ids:
        row = (
            session.execute(
                select(ConnectorCredential).where(
                    ConnectorCredential.user_id == user_id,
                    ConnectorCredential.connector_type == connector_type,
                    ConnectorCredential.account_id == acct,
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            continue
        data = _decrypt_row(row)
        if data:
            return data
    return {}


def stored_connector_credentials(
    session: Session,
    user_id: UUID,
    connector_type: str,
    account_id: str = "",
    project_id: UUID | None = None,
) -> dict:
    """Public best-effort read of a stored credential blob, any shape.

    Used by the manual-credential connectors (apple_ads, meta_ads, stripe,
    revenuecat, openai_ads) whose credential dicts don't fit the Google-shaped
    resolve_execution_creds() output. ``project_id`` (membership-checked by
    the caller) makes the project's bound account win over the caller's own
    rows. Same guarantees: never raises, {} on any miss."""
    return _stored_credentials(
        session, user_id, connector_type, account_id.strip(), project_id=project_id
    )


def resolve_execution_creds(
    session: Session,
    user_id: UUID,
    connector_type: str,
    account_id: str = "",
    override: Mapping[str, str] | None = None,
    project_id: UUID | None = None,
) -> dict[str, str]:
    """Resolve the credentials dict executors expect."""
    cfg = get_configs()
    override = override or {}

    def _ov(key: str) -> str:
        return str(override.get(key) or "").strip()

    stored = _stored_credentials(
        session, user_id, connector_type, account_id.strip(), project_id=project_id
    )

    def _pick(key: str, env_fallback: str = "") -> str:
        return _ov(key) or str(stored.get(key) or "").strip() or env_fallback

    return {
        "refresh_token": _pick("refresh_token"),
        "developer_token": _pick("developer_token", cfg.google_ads_developer_token),
        "login_customer_id": _pick("login_customer_id", cfg.google_ads_login_customer_id),
        "client_id": cfg.google_oauth_client_id or cfg.google_ads_client_id,
        "client_secret": cfg.google_oauth_client_secret or cfg.google_ads_client_secret,
    }
