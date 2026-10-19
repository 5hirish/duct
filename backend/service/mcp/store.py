"""Where a connected MCP server lives: one ``connector_credentials`` row.

No table of its own. A server is a credential with an address, so it is a row
like a PostBridge key is (``service/vendor_keys.py``): ``connector_type`` is
``"mcp"``, ``account_id`` the canonical server URL (one row per server per
user), ``account_name`` what to call it, and the encrypted blob holds the
tokens plus what refreshing them needs.

Servers belong to the user who connected them, and **a project's agent uses
its owner's servers**, the rule vendor keys already follow: the owner chose
what their projects may reach, and a collaborator's run reads through the
owner's connections the way it reads the owner's Google Ads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from models.connector import ConnectorCredential
from models.project import Project
from service.connector_store import upsert_credential
from service.credentials import decrypt_credentials, encrypt_credentials
from service.mcp.oauth import AUTH_KEY, AUTH_NONE, AUTH_OAUTH, ClientRegistration, Tokens
from service.mcp.presets import preset_for_url
from utils.dates import utcnow
from utils.strings import slugify

logger = logging.getLogger(__name__)

MCP_CONNECTOR_TYPE = "mcp"

# Keys inside the encrypted blob.
AUTH = "auth"
API_KEY = "api_key"
ACCESS_TOKEN = "access_token"
REFRESH_TOKEN = "refresh_token"
EXPIRES_AT = "expires_at"
SCOPE = "scope"
TOKEN_ENDPOINT = "token_endpoint"
CLIENT_ID = "client_id"
CLIENT_SECRET = "client_secret"
AUTH_METHOD = "auth_method"
RESOURCE = "resource"
ISSUER = "issuer"
# Set when a refresh is refused: nothing works until the user signs in again,
# and the Connections page says so without a round trip to the server.
NEEDS_REAUTH = "needs_reauth"

STATUS_CONNECTED = "connected"
STATUS_NEEDS_REAUTH = "needs_reauth"


@dataclass(frozen=True)
class ServerAccess:
    """One server as a run reaches it: the address, the name the agent uses,
    and the credentials. Never serialised toward a client."""

    row_id: UUID | None  # None while a connect is still proving the credentials
    key: str
    url: str
    name: str
    credentials: dict
    # Whose account this is. A collaborator's run may read through it; only
    # this user may approve a call that changes something in it.
    owner_id: UUID | None = None

    @property
    def auth(self) -> str:
        return str(self.credentials.get(AUTH) or AUTH_NONE)

    def tokens(self) -> Tokens:
        c = self.credentials
        return Tokens(
            access_token=str(c.get(ACCESS_TOKEN) or ""),
            refresh_token=str(c.get(REFRESH_TOKEN) or ""),
            expires_at=c.get(EXPIRES_AT),
            scope=str(c.get(SCOPE) or ""),
        )

    def registration(self) -> ClientRegistration:
        c = self.credentials
        return ClientRegistration(
            client_id=str(c.get(CLIENT_ID) or ""),
            client_secret=str(c.get(CLIENT_SECRET) or ""),
            auth_method=str(c.get(AUTH_METHOD) or "none"),
        )


def oauth_credentials(
    *, tokens: Tokens, registration: ClientRegistration, token_endpoint: str, resource: str, issuer: str
) -> dict:
    return {
        AUTH: AUTH_OAUTH,
        ACCESS_TOKEN: tokens.access_token,
        REFRESH_TOKEN: tokens.refresh_token,
        EXPIRES_AT: tokens.expires_at,
        SCOPE: tokens.scope,
        TOKEN_ENDPOINT: token_endpoint,
        CLIENT_ID: registration.client_id,
        CLIENT_SECRET: registration.client_secret,
        AUTH_METHOD: registration.auth_method,
        RESOURCE: resource,
        ISSUER: issuer,
    }


def key_credentials(api_key: str) -> dict:
    return {AUTH: AUTH_KEY, API_KEY: api_key}


def no_credentials() -> dict:
    return {AUTH: AUTH_NONE}


def with_tokens(credentials: dict, tokens: Tokens) -> dict:
    return {
        **credentials,
        ACCESS_TOKEN: tokens.access_token,
        REFRESH_TOKEN: tokens.refresh_token,
        EXPIRES_AT: tokens.expires_at,
        SCOPE: tokens.scope or credentials.get(SCOPE, ""),
        NEEDS_REAUTH: False,
    }


def default_name(url: str) -> str:
    preset = preset_for_url(url)
    if preset:
        return preset.label
    return urlsplit(url).hostname or url


def server_keys(rows: list[ConnectorCredential]) -> dict[UUID, str]:
    """The short name the agent calls each server by, unique within ``rows``.

    A preset's id where there is one (``openseo``), else a slug of its name.
    Derived on every read rather than stored, from rows in a stable order, so
    two reads in one run agree.
    """
    keys: dict[UUID, str] = {}
    taken: set[str] = set()
    for row in sorted(rows, key=lambda r: (r.created_at, str(r.id))):
        preset = preset_for_url(row.account_id)
        base = preset.id if preset else (slugify(row.account_name) or "server")
        key, n = base, 2
        while key in taken:
            key, n = f"{base}-{n}", n + 1
        taken.add(key)
        keys[row.id] = key
    return keys


def _readable(row: ConnectorCredential) -> dict:
    """The row's blob, or a stand-in that says "sign in again" when it no
    longer decrypts (a retired key), so one bad row cannot take the listing
    or a run down with it."""
    try:
        return decrypt_credentials(row.credentials_enc)
    except Exception:  # noqa: BLE001 — decrypt raises an HTTPException on a bad token
        logger.warning("mcp: server %s no longer decrypts", row.id)
        return {AUTH: AUTH_OAUTH, NEEDS_REAUTH: True}


def _rows(db: Session, user_id: UUID) -> list[ConnectorCredential]:
    return list(
        db.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == MCP_CONNECTOR_TYPE,
            )
        ).scalars()
    )


def list_servers(db: Session, user_id: UUID) -> list[dict]:
    """The user's servers for the Connections page. No secret leaves here."""
    rows = _rows(db, user_id)
    keys = server_keys(rows)
    out = []
    for row in sorted(rows, key=lambda r: (r.created_at, str(r.id))):
        creds = _readable(row)
        preset = preset_for_url(row.account_id)
        out.append({
            "id": str(row.id),
            "key": keys[row.id],
            "url": row.account_id,
            "name": row.account_name,
            "preset": preset.id if preset else "",
            "auth": str(creds.get(AUTH) or AUTH_NONE),
            "status": STATUS_NEEDS_REAUTH if creds.get(NEEDS_REAUTH) else STATUS_CONNECTED,
            "last_validated_at": row.last_validated_at.isoformat() if row.last_validated_at else None,
            "created_at": row.created_at.isoformat(),
        })
    return out


def save_server(
    db: Session,
    *,
    user_id: UUID,
    url: str,
    name: str,
    credentials: dict,
    validated: bool,
) -> ConnectorCredential:
    """Upsert one server for ``user_id``. Reconnecting replaces the blob. The caller commits."""
    row = upsert_credential(
        db,
        user_id=user_id,
        connector_type=MCP_CONNECTOR_TYPE,
        credentials=credentials,
        granted_scopes=str(credentials.get(SCOPE) or ""),
        account_id=url,
        account_name=(name or "").strip() or default_name(url),
    )
    if validated:
        row.last_validated_at = utcnow()
    return row


def delete_server(db: Session, user_id: UUID, row_id: UUID) -> bool:
    """Remove the user's own server. False for anything else, so the route can
    answer an id it does not own exactly as one that does not exist."""
    row = db.get(ConnectorCredential, row_id)
    if row is None or row.user_id != user_id or row.connector_type != MCP_CONNECTOR_TYPE:
        return False
    db.delete(row)
    return True


def project_owner(db: Session, project_id: UUID) -> UUID | None:
    project = db.get(Project, project_id)
    return project.user_id if project else None


def servers_for_project(db: Session, project_id: UUID) -> list[ServerAccess]:
    """The servers a run on ``project_id`` may use: its owner's.

    ``project_id`` must already be membership-checked; this answers for the
    project, not for the caller.
    """
    owner = project_owner(db, project_id)
    if owner is None:
        return []
    rows = _rows(db, owner)
    keys = server_keys(rows)
    return [
        ServerAccess(
            row_id=row.id,
            key=keys[row.id],
            url=row.account_id,
            name=row.account_name,
            credentials=_readable(row),
            owner_id=owner,
        )
        for row in sorted(rows, key=lambda r: (r.created_at, str(r.id)))
    ]


def has_servers(db: Session, project_id: UUID) -> bool:
    owner = project_owner(db, project_id)
    if owner is None:
        return False
    return (
        db.execute(
            select(ConnectorCredential.id).where(
                ConnectorCredential.user_id == owner,
                ConnectorCredential.connector_type == MCP_CONNECTOR_TYPE,
            ).limit(1)
        ).first()
        is not None
    )


def store_credentials(db: Session, row_id: UUID, credentials: dict, *, validated: bool = False) -> None:
    """Write back what a refresh changed. The caller commits."""
    row = db.get(ConnectorCredential, row_id)
    if row is None:
        return
    row.credentials_enc = encrypt_credentials(credentials)
    row.updated_at = utcnow()
    if validated:
        row.last_validated_at = row.updated_at
    db.add(row)


def mark_validated(db: Session, row_id: UUID) -> None:
    row = db.get(ConnectorCredential, row_id)
    if row is None:
        return
    row.last_validated_at = utcnow()
    db.add(row)
