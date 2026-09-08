"""Writing a connector credential row — the one upsert, wherever it starts.

Two flows store an OAuth grant: the connector's own round-trip, which the app
finishes by posting to ``/api/user/connectors`` (`routes/user_connectors.py`),
and the onboarding sign-in bundle, where the backend holds the refresh token
the moment Google returns it (`service/signin_sources.py`) and no browser is
in a position to post anything. One upsert serves both so that "what a
reconnect keeps" — the account name, the recorded grant — is decided once.

Reads live in ``service/connector_access.py``; this module is only the write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from models.connector import RESIDENCY_SERVER, ConnectorCredential
from service.connector_scopes import join_scopes, parse_scopes
from service.credentials import encrypt_credentials


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
