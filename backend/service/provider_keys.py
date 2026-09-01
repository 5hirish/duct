"""Saved bring-your-own LLM provider keys.

The ``X-Provider-*`` headers are the interactive half of BYOK, and they can
only ever be half: they need a request to ride on. Memory consolidation, the
unattended insights brief, and anything scheduled have no request and no
browser, so header-only BYOK leaves exactly those runs with nothing but Duct's
env key — the thing ``config.allow_server_provider_keys`` exists to stop. This
module is the other half.

Stored on ``connector_credentials`` rather than a table of its own: the row is
already (user, type, account) unique with a Fernet-encrypted blob and a CASCADE
on user delete, which is the whole shape needed. ``connector_type`` is
``llm_provider`` and ``account_id`` is the provider value, so one user holds at
most one key per provider and nothing collides with a real connector.

It also fixes the smaller annoyance: a header key lives in ``sessionStorage``
and dies on refresh, so a customer re-pastes it several times a day.

These values are secrets. They are decrypted only to be spent, never returned
by an API, and never logged — ``has_stored_provider_keys`` exists so the status
endpoint can answer "is one saved?" without a decrypt.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from agents.models import Provider
from models.connector import ConnectorCredential
from service.credentials import decrypt_credentials, encrypt_credentials

logger = logging.getLogger(__name__)

#: Namespace inside ``connector_credentials``. Not a real connector — it has no
#: registry entry, no adapter and no project binding, and must never appear in
#: the data-source catalogue.
CONNECTOR_TYPE = "llm_provider"


def _rows(session: Session, user_id: UUID) -> list[ConnectorCredential]:
    return list(
        session.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == CONNECTOR_TYPE,
            )
        )
        .scalars()
        .all()
    )


def stored_provider_keys(session: Session, user_id: UUID | None) -> dict[Provider, str]:
    """Every provider key this user has saved, decrypted.

    Best-effort by design, exactly like ``connector_access._stored_credentials``:
    a missing CREDENTIALS_ENCRYPTION_KEY or a corrupt token yields ``{}`` and
    the caller falls through to its next source. Raising here would turn a key
    that cannot be read into an outage.
    """
    if user_id is None:
        return {}
    try:
        rows = _rows(session, user_id)
    except Exception:
        logger.warning("provider_keys: lookup failed for user %s", user_id, exc_info=True)
        return {}

    out: dict[Provider, str] = {}
    for row in rows:
        try:
            provider = Provider(row.account_id)
        except ValueError:
            # A provider that has since been removed from the enum. Leave the
            # row alone — it is the user's secret, not ours to delete.
            continue
        try:
            key = (decrypt_credentials(row.credentials_enc) or {}).get("api_key", "")
        except Exception:
            logger.warning(
                "provider_keys: could not decrypt %s for user %s", provider.value, user_id
            )
            continue
        if key and key.strip():
            out[provider] = key.strip()
    return out


def has_stored_provider_keys(session: Session, user_id: UUID | None) -> set[Provider]:
    """Which providers have a saved key, without decrypting any of them."""
    if user_id is None:
        return set()
    try:
        rows = _rows(session, user_id)
    except Exception:
        logger.warning("provider_keys: lookup failed for user %s", user_id, exc_info=True)
        return set()
    out: set[Provider] = set()
    for row in rows:
        try:
            out.add(Provider(row.account_id))
        except ValueError:
            continue
    return out


def save_provider_key(
    session: Session, user_id: UUID, provider: Provider, api_key: str
) -> None:
    """Store (or replace) this user's key for one provider.

    A blank key deletes the row — that is what the settings page sends when
    someone clears the field, and it should not leave the old secret behind.
    """
    key = (api_key or "").strip()
    if not key:
        delete_provider_key(session, user_id, provider)
        return

    row = (
        session.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == CONNECTOR_TYPE,
                ConnectorCredential.account_id == provider.value,
            )
        )
        .scalars()
        .first()
    )
    blob = encrypt_credentials({"api_key": key})
    if row is None:
        row = ConnectorCredential(
            user_id=user_id,
            connector_type=CONNECTOR_TYPE,
            account_id=provider.value,
            account_name=provider.value,
            credentials_enc=blob,
        )
    else:
        row.credentials_enc = blob
    session.add(row)
    session.commit()


def delete_provider_key(session: Session, user_id: UUID, provider: Provider) -> None:
    """Forget this user's saved key for one provider. Idempotent."""
    row = (
        session.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == CONNECTOR_TYPE,
                ConnectorCredential.account_id == provider.value,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return
    session.delete(row)
    session.commit()
