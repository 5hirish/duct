"""Credential resolution for staged execution.

Per-field priority: request override (browser BYO — unchanged behavior) →
stored ``connector_credentials`` row (Fernet-encrypted, saved from the
Connections page) → server env fallback.

Stored rows are what make *agent-initiated* execution possible: an agent
running server-side has no browser session to hand it a refresh token.
Stored lookups try the exact (user, connector_type, account_id) row first,
then the account-agnostic (user, connector_type, "") row.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from config import get_configs
from models.connector import ConnectorCredential
from service.credentials import decrypt_credentials

logger = logging.getLogger(__name__)


def _stored_credentials(
    session: Session, user_id: UUID, connector_type: str, account_id: str
) -> dict:
    """Best-effort decrypt of the user's stored credentials for a connector.

    Never raises: a missing row, a missing CREDENTIALS_ENCRYPTION_KEY, or a
    corrupt token all degrade to ``{}`` so the env fallback still applies.
    """
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
        try:
            data = decrypt_credentials(row.credentials_enc)
        except Exception as exc:  # noqa: BLE001 — stored creds are optional, never fatal
            logger.warning(
                "Could not decrypt stored %s credentials for user %s: %s",
                connector_type,
                user_id,
                exc,
            )
            continue
        if isinstance(data, dict) and data:
            return data
    return {}


def stored_connector_credentials(
    session: Session, user_id: UUID, connector_type: str, account_id: str = ""
) -> dict:
    """Public best-effort read of a user's stored credential blob, any shape.

    Used by the manual-credential connectors (apple_ads, meta_ads, stripe,
    revenuecat, openai_ads) whose credential dicts don't fit the Google-shaped
    resolve_execution_creds() output. Same guarantees: never raises, {} on any
    miss."""
    return _stored_credentials(session, user_id, connector_type, account_id.strip())


def resolve_execution_creds(
    session: Session,
    user_id: UUID,
    connector_type: str,
    account_id: str = "",
    override: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve the credentials dict executors expect."""
    cfg = get_configs()
    override = override or {}

    def _ov(key: str) -> str:
        return str(override.get(key) or "").strip()

    stored = _stored_credentials(session, user_id, connector_type, account_id.strip())

    def _pick(key: str, env_fallback: str = "") -> str:
        return _ov(key) or str(stored.get(key) or "").strip() or env_fallback

    return {
        "refresh_token": _pick("refresh_token"),
        "developer_token": _pick("developer_token", cfg.google_ads_developer_token),
        "login_customer_id": _pick("login_customer_id", cfg.google_ads_login_customer_id),
        "client_id": cfg.google_oauth_client_id or cfg.google_ads_client_id,
        "client_secret": cfg.google_oauth_client_secret or cfg.google_ads_client_secret,
    }
