"""Whether a stored sign-in still works, as the last read found it.

A credential row existing used to be the whole of "Connected", so a Google
sign-in that had been revoked, had expired, or was minted by another OAuth
client kept a green card while every read through it failed. Each reader that
reaches the provider reports what it saw here, and the card follows:

* a refusal Google says only a new sign-in can fix marks the row;
* any read that works, and any fresh credential write, clears it.

Only two refusals count. ``invalid_grant`` is a token Google no longer honours
(revoked, expired, a password change, a testing-mode app's seven days), and
``unauthorized_client`` is a token issued to a different OAuth client, the
desktop app's or production's, which a sign-in from this deployment replaces.
Everything else, ``invalid_client`` included, is the server's configuration or
the network, and telling the user to reconnect would send them round a loop
that cannot fix it.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session

from models.connector import ConnectorCredential
from utils.dates import utcnow

logger = logging.getLogger(__name__)

REFUSED_GRANT_CODES = frozenset({"invalid_grant", "unauthorized_client"})


def is_refused_grant(exc: BaseException) -> bool:
    """True when the provider refused the stored sign-in itself."""
    try:
        from google.auth.exceptions import RefreshError
    except ImportError:  # pragma: no cover - google-auth ships with the backend
        return False
    if not isinstance(exc, RefreshError) or exc.retryable:
        return False
    # google-auth raises RefreshError(message, response_body); the body holds
    # the OAuth error code. Older paths put the code only in the message.
    for arg in exc.args:
        if isinstance(arg, dict) and str(arg.get("error") or "") in REFUSED_GRANT_CODES:
            return True
    message = str(exc.args[0]) if exc.args else ""
    return any(message.startswith(code) for code in REFUSED_GRANT_CODES)


def record_read(session: Session, row_id: UUID, *, refused: bool) -> None:
    """Note what a read through ``row_id`` found. Writes only on a change.

    Never raises: this is bookkeeping beside a read that has already
    succeeded or failed on its own terms, and must not turn either into a 500.
    """
    try:
        row = session.get(ConnectorCredential, row_id)
        if row is None or (row.needs_reconnect_at is not None) == refused:
            return
        row.needs_reconnect_at = utcnow() if refused else None
        session.add(row)
        session.commit()
    except Exception:  # noqa: BLE001 - see docstring
        logger.warning("connector_health: could not record a read on %s", row_id, exc_info=True)
        session.rollback()
