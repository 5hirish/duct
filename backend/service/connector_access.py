"""Connector access — what a project can reach, and with which credentials.

The general question ("what data sources does this project have, and what are
their credentials?"), of which ``service/execution/creds.py`` is one caller:
executors need the same resolution, shaped into the dict the Google clients
expect. That module now builds on this one.

Reads and writes resolve credentials **identically** — the same
binding → stored → env ladder — which is the property that makes an
agent-initiated read safe to reason about alongside an agent-initiated write.

Why this exists at all: the insights pipeline used to take OAuth refresh tokens
from the browser on every request. An agent that discovers mid-run that it needs
Search Console has no browser to go back to, and a scheduled brief has no
browser at all. So credentials resolve server-side, from rows the user already
stored on the Connections page.

Trust model, unchanged from the execution path: ``project_id`` is only ever
passed by a caller that has already checked membership (routes go through
``get_project_for_user``; agent tools receive the id from a membership-gated
session). A bound credential may belong to a different project member than the
caller — deliberately: the project's account is the project's account.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from models.connector import ConnectorCredential, ProjectConnector
from service.credentials import decrypt_credentials

logger = logging.getLogger(__name__)

# What a data source's `status` means, in the order the agent should prefer:
#
#   bound         — the project points this connector at a specific account.
#                   Ready to use; no question needed.
#   available     — the user has stored credentials but this project has not
#                   chosen an account. Needs SelectAccount, not a reconnect.
#   not_connected — nothing stored. Needs RequestConnection.
STATUS_BOUND = "bound"
STATUS_AVAILABLE = "available"
STATUS_NOT_CONNECTED = "not_connected"


@dataclass(frozen=True)
class DataSource:
    """One connector, as the agent sees it."""

    connector_id: str
    label: str
    status: str
    account_id: str = ""
    account_name: str = ""
    last_validated_at: str = ""
    # "oauth" — a browser sign-in the user can complete from a link;
    # "manual" — an API key or key pair they must paste on the Connections page.
    # The agent phrases its ask differently for each, so it needs to know.
    auth_kind: str = "oauth"
    # Whether the insights entity catalog covers this connector, and whether
    # that catalog is overdue an audit. A stale catalog is surfaced rather than
    # hidden: it is exactly the condition that produces plausible wrong numbers.
    has_catalog: bool = False
    catalog_stale: bool = False
    stored_accounts: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "connector_id": self.connector_id,
            "label": self.label,
            "status": self.status,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "last_validated_at": self.last_validated_at,
            "auth_kind": self.auth_kind,
            "has_catalog": self.has_catalog,
            "catalog_stale": self.catalog_stale,
            "stored_accounts": self.stored_accounts,
        }


def bound_credential_row(
    session: Session, project_id: UUID, connector_type: str
) -> ConnectorCredential | None:
    """The credential row a project has bound for one connector type, or None."""
    return (
        session.execute(
            select(ConnectorCredential)
            .join(
                ProjectConnector,
                ProjectConnector.connector_credential_id == ConnectorCredential.id,
            )
            .where(
                ProjectConnector.project_id == project_id,
                ProjectConnector.connector_type == connector_type,
            )
        )
        .scalars()
        .first()
    )


def _decrypt_row(row: ConnectorCredential) -> dict:
    try:
        data = decrypt_credentials(row.credentials_enc)
    except Exception as exc:  # noqa: BLE001 — stored creds are optional, never fatal
        logger.warning(
            "Could not decrypt stored %s credentials (row %s): %s",
            row.connector_type,
            row.id,
            exc,
        )
        return {}
    return data if isinstance(data, dict) else {}


def _stored_credentials(
    session: Session,
    user_id: UUID,
    connector_type: str,
    account_id: str,
    project_id: UUID | None = None,
) -> dict:
    """Best-effort decrypt of the credentials for a connector.

    Project binding first (when ``project_id`` is given), then the caller's
    own rows. Never raises: a missing row, a missing
    CREDENTIALS_ENCRYPTION_KEY, or a corrupt token all degrade to ``{}`` so
    the env fallback still applies.
    """
    if project_id is not None:
        bound = bound_credential_row(session, project_id, connector_type)
        # An explicitly-targeted different account skips the binding: the
        # caller asked for account Y, the project is bound to account X — the
        # caller's own rows for Y are the honest source, not X's secrets.
        if bound is not None and not (
            account_id and bound.account_id and bound.account_id != account_id
        ):
            data = _decrypt_row(bound)
            if data:
                return data
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
        data = _decrypt_row(row)
        if data:
            return data
    return {}


def stored_connector_credentials(
    session: Session,
    user_id: UUID,
    connector_type: str,
    account_id: str = "",
    project_id: UUID | None = None,
) -> dict:
    """Public best-effort read of a stored credential blob, any shape.

    Used by the manual-credential connectors (apple_ads, meta_ads, stripe,
    revenuecat, openai_ads) whose credential dicts don't fit the Google-shaped
    resolve_execution_creds() output. ``project_id`` (membership-checked by
    the caller) makes the project's bound account win over the caller's own
    rows. Same guarantees: never raises, {} on any miss."""
    return _stored_credentials(
        session, user_id, connector_type, account_id.strip(), project_id=project_id
    )



# ---------------------------------------------------------------------------
# Credentials for a read
# ---------------------------------------------------------------------------

# Connectors whose clients want the Google OAuth shape (refresh token + the
# app's own client id/secret) rather than the stored blob as-is.
_GOOGLE_SHAPED = frozenset({"google_ads", "ga4", "gsc", "gtm"})


def resolve_read_credentials(
    session: Session,
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    connector_type: str,
    account_id: str = "",
) -> dict[str, str]:
    """Credentials for reading one connector, resolved server-side.

    The read counterpart of ``resolve_execution_creds`` and deliberately the
    same ladder, so a read and a write in the same session cannot disagree about
    which account they are talking to. No request override: a read initiated by
    an agent has no browser to take a token from, which is the entire reason
    this exists.

    Returns ``{}`` when nothing is stored — callers treat that as "not
    connected", never as an error.
    """
    stored = _stored_credentials(session, user_id, connector_type, account_id.strip(), project_id=project_id)
    if connector_type not in _GOOGLE_SHAPED:
        # Manual-credential connectors carry their own shape (api_key, team_id,
        # private_key, …) — hand it back untouched.
        return {str(k): str(v) for k, v in stored.items() if v}
    if not stored:
        return {}

    from config import get_configs

    cfg = get_configs()
    resolved = {
        "refresh_token": str(stored.get("refresh_token") or "").strip(),
        "developer_token": str(stored.get("developer_token") or "").strip() or cfg.google_ads_developer_token,
        "login_customer_id": str(stored.get("login_customer_id") or "").strip() or cfg.google_ads_login_customer_id,
        "client_id": cfg.google_oauth_client_id or cfg.google_ads_client_id,
        "client_secret": cfg.google_oauth_client_secret or cfg.google_ads_client_secret,
    }
    return {k: v for k, v in resolved.items() if v}


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _catalog_state(connector_id: str) -> tuple[bool, bool]:
    """(has_catalog, is_stale) for one connector — never raises."""
    try:
        from agents.insights.catalog import get_catalog_for_connector, is_catalog_stale

        catalog = get_catalog_for_connector(connector_id)
        if not catalog:
            return False, False
        return True, is_catalog_stale(catalog)
    except Exception:  # noqa: BLE001 — a broken catalog must not hide the connector
        logger.warning("connector_access: catalog check failed for %s", connector_id, exc_info=True)
        return False, False


def list_data_sources(
    session: Session,
    *,
    user_id: UUID | None,
    project_id: UUID | None = None,
) -> list[DataSource]:
    """Every connector Duct supports, and where this project stands on each.

    Returns the full registry — including connectors with nothing stored — because
    "not connected" is the answer the agent most needs: it is what turns into an
    offer to connect. Ordered so the ready ones come first.
    """
    from service.connectors import registry

    stored: dict[str, list[ConnectorCredential]] = {}
    if user_id is not None:
        rows = (
            session.execute(
                select(ConnectorCredential)
                .where(ConnectorCredential.user_id == user_id)
                .order_by(ConnectorCredential.connector_type, ConnectorCredential.account_name)
            )
            .scalars()
            .all()
        )
        for row in rows:
            stored.setdefault(row.connector_type, []).append(row)

    bindings: dict[str, ConnectorCredential] = {}
    if project_id is not None:
        bound_rows = session.execute(
            select(ProjectConnector, ConnectorCredential).join(
                ConnectorCredential,
                ConnectorCredential.id == ProjectConnector.connector_credential_id,
            ).where(ProjectConnector.project_id == project_id)
        ).all()
        for binding, cred in bound_rows:
            bindings[binding.connector_type] = cred

    sources: list[DataSource] = []
    for connector_id, (meta, _adapter) in registry().items():
        has_catalog, catalog_stale = _catalog_state(connector_id)
        rows = stored.get(connector_id, [])
        bound = bindings.get(connector_id)
        if bound is not None:
            status, account_id, account_name = STATUS_BOUND, bound.account_id, bound.account_name
            validated = bound.last_validated_at
        elif rows:
            # One stored account and no binding is not ambiguous — treat the
            # single row as the account, so the agent does not ask a question
            # with exactly one possible answer.
            only = rows[0] if len(rows) == 1 else None
            status = STATUS_AVAILABLE
            account_id = only.account_id if only else ""
            account_name = only.account_name if only else ""
            validated = only.last_validated_at if only else None
        else:
            status, account_id, account_name, validated = STATUS_NOT_CONNECTED, "", "", None

        sources.append(
            DataSource(
                connector_id=connector_id,
                label=meta.label,
                status=status,
                account_id=account_id,
                account_name=account_name,
                last_validated_at=validated.isoformat() if validated else "",
                auth_kind="oauth" if meta.oauth_scope else "manual",
                has_catalog=has_catalog,
                catalog_stale=catalog_stale,
                stored_accounts=[
                    {"account_id": r.account_id, "account_name": r.account_name}
                    for r in rows
                ],
            )
        )

    order = {STATUS_BOUND: 0, STATUS_AVAILABLE: 1, STATUS_NOT_CONNECTED: 2}
    return sorted(sources, key=lambda s: (order.get(s.status, 9), s.connector_id))


def get_data_source(
    session: Session,
    connector_id: str,
    *,
    user_id: UUID | None,
    project_id: UUID | None = None,
) -> DataSource | None:
    """One connector's state, or None when the id is not in the registry."""
    for source in list_data_sources(session, user_id=user_id, project_id=project_id):
        if source.connector_id == connector_id:
            return source
    return None


def bind_project_account(
    session: Session,
    *,
    project_id: UUID,
    user_id: UUID,
    connector_type: str,
    account_id: str,
) -> ConnectorCredential | None:
    """Point a project's connector at one of the caller's stored accounts.

    The write half of SelectAccount: once the user picks, the choice persists as
    a ``project_connectors`` row so no later session has to ask again. Ownership
    is enforced here — you may offer your own account to a project, never point
    it at someone else's row (``routes/project_connectors.py`` holds the same
    rule for the HTTP path). Returns None when no such row belongs to the caller.
    """
    row = (
        session.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == connector_type,
                ConnectorCredential.account_id == account_id.strip(),
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None

    binding = (
        session.execute(
            select(ProjectConnector).where(
                ProjectConnector.project_id == project_id,
                ProjectConnector.connector_type == connector_type,
            )
        )
        .scalars()
        .first()
    )
    if binding is None:
        binding = ProjectConnector(
            project_id=project_id,
            connector_type=connector_type,
            connector_credential_id=row.id,
        )
    else:
        binding.connector_credential_id = row.id
    session.add(binding)
    session.commit()
    return row


def attach_account(
    session: Session,
    *,
    project_id: UUID,
    user_id: UUID,
    connector_type: str,
    account_id: str,
    account_name: str = "",
) -> ConnectorCredential | None:
    """Record a chosen account for an already-authorized connector, then bind it.

    The case that replaces wizard steps 2–4. After OAuth the user has one
    account-agnostic credential row (``account_id=""``) — authorized, but with no
    property/customer/site chosen. Picking one upserts an account-specific row
    carrying the same secret, exactly as saving from the Connections page does,
    and points the project at it. The state left behind is indistinguishable
    from the user having done it by hand.

    Returns None when there is no authorized row to copy from — the caller
    should be asking for a connection, not an account.
    """
    from service.credentials import encrypt_credentials

    account_id = account_id.strip()
    if not account_id:
        return None

    rows = (
        session.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.user_id == user_id,
                ConnectorCredential.connector_type == connector_type,
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None

    exact = next((r for r in rows if r.account_id == account_id), None)
    if exact is not None:
        if account_name and not exact.account_name:
            exact.account_name = account_name
            session.add(exact)
            session.commit()
        return bind_project_account(
            session, project_id=project_id, user_id=user_id,
            connector_type=connector_type, account_id=account_id,
        )

    # Copy the secret from whichever authorized row we have — prefer the
    # account-agnostic one, since that is what a fresh OAuth leaves behind.
    donor = next((r for r in rows if not r.account_id), rows[0])
    blob = _decrypt_row(donor)
    if not blob:
        return None

    row = ConnectorCredential(
        user_id=user_id,
        connector_type=connector_type,
        account_id=account_id,
        account_name=account_name,
        credentials_enc=encrypt_credentials(blob),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return bind_project_account(
        session, project_id=project_id, user_id=user_id,
        connector_type=connector_type, account_id=account_id,
    )
