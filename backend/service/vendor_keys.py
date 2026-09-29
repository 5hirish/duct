"""Third-party keys each user brings for themselves: PostBridge, Apify.

Hosted Duct held keys of its own for both, and spent them on whoever asked:
the PostBridge one listed the operator's social accounts to anyone who signed
up and published to them, and the Apify one paid for every signup's scraping.
Spending an instance's key on a customer's request is the thing
bring-your-own-key exists to prevent, so a request spends the key its
project's owner saved (a ``connector_credentials`` row, encrypted), and the
instance's env key only where ``allow_server_provider_keys()`` holds: local dev
and the desktop sidecar, where the env file is the user's own.

A project spends its owner's key, the way it spends its owner's connectors, so
only the owner connects one. The routes are generic over ``VENDOR_KEYS`` in
``routes/content.py``; each vendor declares one ``VendorKey`` beside its client
with a ``check``: the cheapest authenticated read that proves a pasted key works.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from config import allow_server_provider_keys, get_configs
from models.connector import ConnectorCredential
from models.project import Project
from service.connector_store import upsert_credential
from service.credentials import decrypt_credentials

# Where a request's key came from, for the status route.
KEY_OWN = "own"
KEY_SERVER = "server"


class VendorNotConnected(ValueError):
    """No key this request may spend. A ValueError, so the routes that already
    answered 400 for a missing key keep doing so."""


class VendorKeyRejected(Exception):
    """The vendor refused a pasted key: its 401 or 403."""


class VendorKeyUnchecked(Exception):
    """The vendor could not be asked about a key: down, rate-limited, unreachable."""


@dataclass(frozen=True)
class VendorKey:
    connector_type: str  # ConnectorCredential.connector_type
    setting: str         # the Configs attribute holding the instance's own key
    label: str           # "PostBridge", in sentences
    where: str           # where a user pastes theirs
    check: Callable[[str], Awaitable[None]]  # raises VendorKeyRejected / VendorKeyUnchecked

    @property
    def not_connected(self) -> str:
        return f"{self.label} isn't connected yet. Paste your {self.label} API key in {self.where}."

    def _rows(self, user_id: UUID, db: Session) -> list[ConnectorCredential]:
        return list(db.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == self.connector_type,
            )
        ).scalars())

    def saved(self, user_id: UUID, db: Session) -> str:
        for row in self._rows(user_id, db):
            creds = decrypt_credentials(row.credentials_enc)
            key = creds.get("api_key") or creds.get("token") or ""  # "token": rows written before the field had a name
            if key:
                return key
        return ""

    def server(self) -> str:
        """The instance's own key, where it may be spent: local and desktop."""
        key = (getattr(get_configs(), self.setting, "") or "").strip()
        return key if key and allow_server_provider_keys() else ""

    def source(self, user_id: UUID, db: Session) -> str | None:
        if self.saved(user_id, db):
            return KEY_OWN
        if self.server():
            return KEY_SERVER
        return None

    def resolve(self, user_id: UUID, db: Session) -> str:
        """The key a request for ``user_id`` spends, or VendorNotConnected."""
        key = self.saved(user_id, db) or self.server()
        if not key:
            raise VendorNotConnected(self.not_connected)
        return key

    def for_project(self, project_id: UUID, db: Session) -> str:
        """The project owner's key, or "" — for background work that degrades
        rather than fails without one."""
        project = db.get(Project, project_id)
        if project is None:
            return ""
        return self.saved(project.user_id, db) or self.server()

    def save(self, user_id: UUID, api_key: str, db: Session) -> None:
        """Store a key ``check`` accepted, replacing the user's last. The caller commits."""
        upsert_credential(
            db, user_id=user_id, connector_type=self.connector_type,
            credentials={"api_key": api_key}, account_name=self.label,
        )

    def forget(self, user_id: UUID, db: Session) -> None:
        """The caller commits."""
        for row in self._rows(user_id, db):
            db.delete(row)
