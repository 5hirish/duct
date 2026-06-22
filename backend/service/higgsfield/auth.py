"""Resolve the Higgsfield bearer token for a user.

Mirrors service/post_bridge/client.py:_api_key_for_user — prefer the user's
stored ConnectorCredential (written by the frontend OAuth connect flow), and
fall back to the server-wide HIGGSFIELD_API_TOKEN for dev / single-operator use.

The token is replayed as ``Authorization: Bearer <token>`` against Higgsfield's
hosted MCP from the headless content runner (see agents/content/v3/runner.py).
Prefer a long-lived Higgsfield CLI/API token for the env fallback — short-lived
OAuth access tokens need refresh (TODO below) to survive a backend run.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from config import get_configs
from models.connector import ConnectorCredential
from service.credentials import decrypt_credentials

CONNECTOR_TYPE = "higgsfield"
MCP_URL = "https://mcp.higgsfield.ai/mcp"

# Credential-blob keys we accept, in priority order. The connect flow may store
# an OAuth access token, a generic token, or a long-lived CLI/API token.
_TOKEN_KEYS = ("access_token", "token", "api_token", "api_key")


def _token_from_credential(row: ConnectorCredential) -> str:
    creds = decrypt_credentials(row.credentials_enc)
    # TODO(refresh): when creds carry {refresh_token, expires_at} and the access
    # token is expired, exchange the refresh_token at Higgsfield's token endpoint,
    # persist the new blob, and return the fresh access_token. Until the OAuth
    # connect flow lands we just return the stored token.
    for key in _TOKEN_KEYS:
        val = creds.get(key)
        if val:
            return str(val)
    return ""


def higgsfield_token_for_user(user_id: UUID | None, db: Session) -> str:
    """Return a usable Higgsfield bearer token, or "" if none is connected.

    Callers treat "" as "Higgsfield not connected" and skip wiring the MCP /
    surface a connect prompt to the user (rather than raising) — drafting a
    video without a token should fail soft, not crash the run.
    """
    if user_id is not None:
        row = db.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == CONNECTOR_TYPE,
            )
        ).scalars().first()
        if row is not None:
            token = _token_from_credential(row)
            if token:
                return token

    return (getattr(get_configs(), "higgsfield_api_token", "") or "").strip()


def higgsfield_mcp_config(token: str) -> dict:
    """Build the remote HTTP MCP server config for ClaudeAgentOptions.mcp_servers.

    The Claude Agent SDK does not run OAuth itself; it just replays this bearer.
    """
    return {
        "type": "http",
        "url": MCP_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }
