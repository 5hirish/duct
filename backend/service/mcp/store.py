"""Where a connected MCP server lives: one ``connector_credentials`` row.

No table of its own. A server is a credential with an address, so it is a row
like a PostBridge key is (``service/vendor_keys.py``): ``connector_type`` is
``"mcp"``, ``account_id`` the canonical server URL (one row per server per
user), ``account_name`` what to call it, and the encrypted blob holds the
tokens plus what refreshing them needs.

Servers belong to the user who connected them, and **a chat reaches only its
own user's servers**, in whichever project it runs. Not the project owner's,
the rule vendor keys follow: a key spends money on the project's behalf, but
an MCP token reads the whole account behind it (every Notion page, not the
project's), and nothing binds a server to one project. Sessions are their
creator's alone (``routes/agents.py``, ``_owned_session``), so the person who
sees a server's data and answers its approval card is always its owner.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from models.connector import ConnectorCredential
from service.connector_store import upsert_credential
from service.credentials import decrypt_credentials, encrypt_credentials
from service.mcp.oauth import AUTH_KEY, AUTH_NONE, AUTH_OAUTH, ClientRegistration, Tokens
from service.mcp.presets import preset_for_url
from utils.dates import now_iso, utcnow
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
# Why the server needs its owner, for the card's "Needs attention" line.
# Written by the client (``client.py``) when a listing fails or a refresh is
# refused, cleared by the next call that works or by a reconnect, which
# replaces the blob. Beside NEEDS_REAUTH rather than in a column because it
# changes when the credentials do, and the listing already reads them. Unlike
# NEEDS_REAUTH it stops nothing: a server that was down at 3am is asked again.
PROBLEM = "problem"
PROBLEM_AT = "problem_at"
PROBLEM_SIGNED_OUT = "signed_out"  # the sign-in expired or was revoked
PROBLEM_KEY_REFUSED = "key_refused"
PROBLEM_AUTH_REQUIRED = "auth_required"  # connected with no sign-in, now wants one
PROBLEM_UNREADABLE = "unreadable"  # the saved blob no longer decrypts
PROBLEM_UNREACHABLE = "unreachable"
PROBLEM_FAILING = "failing"  # it answers, with an error
_REAUTH_PROBLEMS = frozenset({PROBLEM_SIGNED_OUT, PROBLEM_KEY_REFUSED, PROBLEM_AUTH_REQUIRED, PROBLEM_UNREADABLE})

STATUS_CONNECTED = "connected"
STATUS_NEEDS_REAUTH = "needs_reauth"  # only the person can fix it: sign in, or a new key
STATUS_FAILING = "failing"  # nothing to fix on our side yet; the server is down or erring


@dataclass(frozen=True)
class ServerAccess:
    """One server as a run reaches it: the address, the name the agent uses,
    and the credentials. Never serialised toward a client."""

    row_id: UUID | None  # None while a connect is still proving the credentials
    key: str
    url: str
    name: str
    credentials: dict

    @property
    def vetted(self) -> bool:
        """A preset whose ``readOnlyHint`` Duct believes (``trust_read_only``).
        On a server added by address it is the stranger's own claim, and a
        tool that says it only reads can still carry whatever the agent puts
        in its arguments to that stranger; on an infrastructure preset the
        read itself returns secrets."""
        found = preset_for_url(self.url)
        return bool(found and found.trust_read_only)

    @property
    def is_preset(self) -> bool:
        return preset_for_url(self.url) is not None

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


def with_problem(credentials: dict, problem: str) -> dict:
    return {**credentials, PROBLEM: problem, PROBLEM_AT: now_iso()}


def without_problem(credentials: dict) -> dict:
    return {k: v for k, v in credentials.items() if k not in (PROBLEM, PROBLEM_AT)}


def problem_of(credentials: dict) -> str:
    """The recorded reason, or "signed_out" for a blob flagged before reasons
    were recorded, or "" when nothing is wrong."""
    return str(credentials.get(PROBLEM) or (PROBLEM_SIGNED_OUT if credentials.get(NEEDS_REAUTH) else ""))


def status_of(problem: str) -> str:
    if not problem:
        return STATUS_CONNECTED
    return STATUS_NEEDS_REAUTH if problem in _REAUTH_PROBLEMS else STATUS_FAILING


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
        return {AUTH: AUTH_OAUTH, NEEDS_REAUTH: True, PROBLEM: PROBLEM_UNREADABLE}


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
        problem = problem_of(creds)
        out.append({
            "id": str(row.id),
            "key": keys[row.id],
            "url": row.account_id,
            "name": row.account_name,
            "preset": preset.id if preset else "",
            "auth": str(creds.get(AUTH) or AUTH_NONE),
            "status": status_of(problem),
            "problem": problem,
            "problem_at": creds.get(PROBLEM_AT) if problem else None,
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


def servers_for_user(db: Session, user_id: UUID) -> list[ServerAccess]:
    """The servers a chat run by ``user_id`` may use: their own, oldest first."""
    rows = _rows(db, user_id)
    keys = server_keys(rows)
    return [
        ServerAccess(
            row_id=row.id,
            key=keys[row.id],
            url=row.account_id,
            name=row.account_name,
            credentials=_readable(row),
        )
        for row in sorted(rows, key=lambda r: (r.created_at, str(r.id)))
    ]


def server_for_user(db: Session, user_id: UUID, row_id: UUID) -> ServerAccess | None:
    """One of the user's own servers, or None for anyone else's."""
    return next((s for s in servers_for_user(db, user_id) if s.row_id == row_id), None)


def has_servers(db: Session, user_id: UUID) -> bool:
    return (
        db.execute(
            select(ConnectorCredential.id).where(
                ConnectorCredential.user_id == user_id,
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
