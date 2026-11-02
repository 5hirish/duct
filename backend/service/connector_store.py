"""Writing a connector credential row — the one upsert, wherever it starts.

Two flows store a Google OAuth grant, and in both the backend is the only
party that ever holds the refresh token: the connector's own round-trip, whose
grant the signed-in page claims (``POST /api/user/connectors/claim``,
`routes/user_connectors.py`), and the onboarding sign-in bundle, stored the
moment Google returns it (`service/signin_sources.py`). The manual connectors
post their pasted keys to ``/api/user/connectors``. One upsert serves all of
them so that "what a reconnect keeps" — the account name, the recorded grant —
is decided once.

Reads live in ``service/connector_access.py``; this module is only the write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from models.connector import RESIDENCY_SERVER, ConnectorCredential
from service.connector_access import decrypt_row
from service.connector_scopes import join_scopes, parse_scopes
from service.credentials import decrypt_credentials, encrypt_credentials
from service.google.constants import REFRESH_TOKEN_KEY


def upsert_credential(
    session: Session,
    *,
    user_id: UUID,
    connector_type: str,
    credentials: dict,
    granted_scopes: str = "",
    account_id: str = "",
    account_name: str = "",
    residency: str = RESIDENCY_SERVER,
) -> ConnectorCredential:
    """Store ``credentials`` for one (user, connector, account), replacing any
    existing blob whole.

    ``granted_scopes`` only overwrites when this save actually carries a grant:
    a later save that does not know the scopes — an account rename, a manual
    re-save — must not erase what the OAuth round-trip recorded. The caller
    commits; a route wants its own transaction boundary and so does a callback
    that stores two rows from one consent.
    """
    account_id = account_id.strip()
    existing = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user_id,
            ConnectorCredential.connector_type == connector_type,
            ConnectorCredential.account_id == account_id,
        )
    ).scalars().first()

    now = datetime.now(timezone.utc)
    enc = encrypt_credentials(credentials)
    granted = join_scopes(parse_scopes(granted_scopes))

    if existing is not None:
        existing.account_name = account_name
        existing.credentials_enc = enc
        existing.residency = residency
        if granted:
            existing.granted_scopes = granted
        existing.updated_at = now
        session.add(existing)
        return existing

    row = ConnectorCredential(
        user_id=user_id,
        connector_type=connector_type,
        account_id=account_id,
        account_name=account_name,
        credentials_enc=enc,
        residency=residency,
        granted_scopes=granted,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    return row


def _owned_row(
    session: Session, *, user_id: UUID, connector_type: str, account_id: str
) -> ConnectorCredential | None:
    return session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user_id,
            ConnectorCredential.connector_type == connector_type,
            ConnectorCredential.account_id == account_id,
        )
    ).scalars().first()


def store_oauth_grant(
    session: Session,
    *,
    user_id: UUID,
    connector_type: str,
    refresh_token: str,
    granted_scopes: str = "",
) -> ConnectorCredential:
    """Put a fresh refresh token on the user's account-agnostic row for a connector.

    Merged over what the row already holds rather than replacing it, because
    the token is not the whole blob: a Google Ads reconnect must keep the
    manager (MCC) id the user set, or reconnecting quietly breaks every read
    through that manager. ``upsert_credential`` replaces whole, which is right
    for a pasted key and wrong here. The caller commits.
    """
    existing = _owned_row(session, user_id=user_id, connector_type=connector_type, account_id="")
    kept = decrypt_row(existing) if existing is not None else {}
    return upsert_credential(
        session,
        user_id=user_id,
        connector_type=connector_type,
        credentials={**kept, REFRESH_TOKEN_KEY: refresh_token},
        granted_scopes=granted_scopes,
        account_name=existing.account_name if existing is not None else "",
        residency=(existing.residency if existing is not None else "") or RESIDENCY_SERVER,
    )


def merge_settings(row: ConnectorCredential, settings: dict[str, str]) -> ConnectorCredential:
    """Set or clear non-secret keys on a stored row, leaving every other key alone.

    An empty value removes the key, so clearing the MCC field falls back to the
    server's default rather than storing "". The caller has already checked the
    keys against the connector's ``settings_keys`` and commits.

    Decrypts strictly, unlike a reconnect: a blob that cannot be read still
    holds a token, and writing the settings over it would destroy the token to
    save an account id.
    """
    blob = decrypt_credentials(row.credentials_enc)
    for key, value in settings.items():
        value = (value or "").strip()
        if value:
            blob[key] = value
        else:
            blob.pop(key, None)
    row.credentials_enc = encrypt_credentials(blob)
    row.updated_at = datetime.now(timezone.utc)
    return row
