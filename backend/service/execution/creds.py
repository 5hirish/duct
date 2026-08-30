"""Credential resolution for staged execution.

The executor-shaped specialization of ``service/connector_access.py``: that
module answers "what are this project's credentials for connector X" for reads
and writes alike; this one folds in a request override and the server env
fallback, and returns the exact dict the Google clients expect.

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

from sqlmodel import Session

from config import get_configs
from service.connector_access import _stored_credentials

logger = logging.getLogger(__name__)


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
