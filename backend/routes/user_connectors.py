"""Connector credential endpoints — GET/POST/DELETE /api/user/connectors."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

from db.session import STORAGE_CLOUD, STORAGE_LOCAL, get_session, storage_location
from models.auth import User
from models.connector import (
    RESIDENCIES,
    RESIDENCY_DEVICE,
    RESIDENCY_SERVER,
    ConnectorCredential,
)
from service.auth import get_current_user
from service.connector_access import list_data_sources
from service.connector_scopes import (
    SCOPE_NA,
    missing_scopes,
    parse_scopes,
    scope_rows,
    scope_status,
)
from service.auth_exchange import consume_github_grant, store_connect_link_code
from service.connector_store import upsert_credential
from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    get_connector,
    registry,
    server_only_keys_in,
)
from service.credentials import decrypt_credentials
from service.github import GITHUB_CONNECTOR_ID
from service.github import app as gh_app
from service.provider_keys import CONNECTOR_TYPE as PROVIDER_KEY_TYPE

router = APIRouter(tags=["user-connectors"])

ALLOWED_CONNECTOR_TYPES = {
    "google_ads", "ga4", "gsc", "gtm",
    # Manual-credential connectors (Phase 7) — Fernet JSON blobs fit any shape.
    "apple_ads", "meta_ads", "stripe", "revenuecat", "openai_ads",
    # Gads wave 2 — the cross-check + behaviour sources.
    "mixpanel", "clarity", "growthbook",
    # What shipped, and when (issue #268). Opens project binding too:
    # routes/project_connectors.py checks this same set.
    GITHUB_CONNECTOR_ID,
}


class ConnectorIn(BaseModel):
    connector_type: str          # 'google_ads' | 'ga4' | 'gsc' | 'gtm'
    account_id: str = ""         # customer_id / property_id / site_url
    account_name: str = ""
    credentials: dict            # raw dict — will be encrypted at rest
    # What the provider actually consented to, space-separated. Optional: a
    # manual-credential save has none, and an OAuth save made by an older client
    # has none either — both correctly land as "unknown" rather than "none".
    granted_scopes: str = ""
    # "server" (default) or "device". Device-only credentials are refused by a
    # backend whose database it does not own — see `_check_residency`.
    residency: str = RESIDENCY_SERVER
    # What this connector calls the thing a project maps to. Sent with the row
    # so a picker can label itself correctly on first paint — it used to say
    # "Account" over a list of Search Console properties until the dropdown was
    # opened, because the nouns only arrived with the (lazy, network) entity
    # listing.
    entity_noun: str = "account"
    entity_noun_plural: str = "accounts"


class ConnectorOut(BaseModel):
    id: UUID
    connector_type: str
    account_id: str
    account_name: str
    last_validated_at: str | None
    created_at: str
    updated_at: str
    # The scope picture, joined here so the browser needs no catalog of its own:
    # `scopes` carries one row per scope this connector asks for, each with the
    # justification the user is entitled to read before granting it.
    granted_scopes: list[str] = []
    missing_scopes: list[str] = []
    scope_status: str = SCOPE_NA
    scopes: list[dict] = []
    # Where this row physically lives, so the browser can say so without
    # guessing. It cannot work this out for itself: the only thing the page can
    # observe is that a local sidecar answered, which is true even when that
    # sidecar is storing into a deployment's Postgres.
    storage: str = STORAGE_CLOUD
    # Where the user said it may live, as distinct from where it is. The two
    # agree for every row written through this API — the save path refuses the
    # combination that would make them disagree — but they are different
    # questions and the UI has reason to show both.
    residency: str = RESIDENCY_SERVER
    # What this connector calls the thing a project maps to. Sent with the row
    # so a picker labels itself correctly on first paint — it used to read
    # "Account" over a list of Search Console properties until the dropdown was
    # opened, because the nouns only arrived with the lazy entity listing.
    entity_noun: str = "account"
    entity_noun_plural: str = "accounts"



def _to_out(c: ConnectorCredential) -> ConnectorOut:
    entry = registry().get(c.connector_type)
    declared = parse_scopes(entry[0].oauth_scope) if entry else []
    granted = parse_scopes(c.granted_scopes)
    is_oauth = bool(entry and entry[0].oauth_scope)
    return ConnectorOut(
        id=c.id,
        connector_type=c.connector_type,
        account_id=c.account_id,
        account_name=c.account_name,
        last_validated_at=c.last_validated_at.isoformat() if c.last_validated_at else None,
        created_at=c.created_at.isoformat(),
        updated_at=c.updated_at.isoformat(),
        granted_scopes=granted,
        missing_scopes=missing_scopes(declared, granted) if (is_oauth and granted) else [],
        scope_status=scope_status(is_oauth=is_oauth, declared=declared, granted=granted),
        scopes=scope_rows(declared, granted) if is_oauth else [],
        storage=storage_location(),
        residency=c.residency or RESIDENCY_SERVER,
        entity_noun=entry[0].entity_noun if entry else "account",
        entity_noun_plural=entry[0].entity_noun_plural if entry else "accounts",
    )


@router.get("")
def list_connectors(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ConnectorOut]:
    rows = session.execute(
        select(ConnectorCredential)
        .where(ConnectorCredential.user_id == user.id)
        # Saved LLM provider keys share this table (service/provider_keys.py)
        # but are not connectors: no registry entry, no adapter, no account to
        # bind. Without this they surface here as a phantom row the Connections
        # page would render as a data source nobody can configure.
        .where(ConnectorCredential.connector_type != PROVIDER_KEY_TYPE)
        .order_by(ConnectorCredential.connector_type, ConnectorCredential.account_name)
    ).scalars().all()
    return [_to_out(r) for r in rows]



@router.get("/{row_id}/entities")
def list_connector_entities(
    row_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """The things this stored connector can actually read, for the project picker.

    Distinct from `/api/connectors/{id}/accounts`, which takes credentials in the
    request body — fine for a manual connector the user is in the middle of
    pasting, wrong for a saved one: the browser holds no refresh token for an
    OAuth connector and must never be handed one just to render a dropdown. So
    this resolves the credential server-side from a row the caller owns.

    404 rather than 403 for a row belonging to someone else, so the response is
    not an oracle for which credential ids exist.
    """
    row = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.id == row_id,
            ConnectorCredential.user_id == user.id,
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Connector not found")

    try:
        meta, adapter = get_connector(row.connector_type)
    except KeyError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Unknown connector") from exc

    # Not every connector has anything to pick. Say so as data rather than as an
    # error: the picker hides itself, and the caller needs the nouns regardless.
    if CAP_ACCOUNTS not in meta.capabilities:
        return {"entities": [], "supported": False, **_entity_nouns(meta)}

    stored = decrypt_credentials(row.credentials_enc)
    refresh_token = str(stored.get("refresh_token") or "").strip()
    extras = {
        key: str(value).strip()
        for key, value in stored.items()
        if key != "refresh_token" and value and str(value).strip()
    }
    auth = ConnectorAuthContext(
        connector_id=row.connector_type,
        refresh_token=refresh_token or None,
        extras=extras,
    )
    try:
        entities = adapter.list_accounts(auth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"entities": entities, "supported": True, **_entity_nouns(meta)}


def _entity_nouns(meta) -> dict:  # noqa: ANN001 — ConnectorMeta, avoids an import cycle
    return {"entity_noun": meta.entity_noun, "entity_noun_plural": meta.entity_noun_plural}


@router.get("/data-sources")
def list_account_data_sources(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """The same inventory as the project route, with no project in the picture.

    Needed because the first thing the onboarding checklist asks for is a
    PROJECT: someone who has connected three sources but not yet created one
    has no project id to ask about, and telling them they have connected
    nothing is how they end up connecting a fourth.

    Without a project there are no bindings, so every stored connector reports
    ``available`` rather than ``bound`` — which is the truth: the credential
    exists, nothing has chosen an account for it yet.
    """
    return [source.as_dict() for source in list_data_sources(session, user_id=user.id)]


def _check_residency(residency: str) -> str:
    """Refuse to write a device-only credential into a database we do not own.

    The point of the flag is that it is a rule. A desktop build pointed at a
    shared Postgres — which is how the app is developed against staging — would
    otherwise accept "keep this on my machine" and then write it to a server,
    and nothing downstream would ever contradict the label. Failing the write is
    the only honest answer: the user asked for something this backend cannot do.

    `storage_location()` is the right test rather than `duct_local`, for the
    same reason it is elsewhere: every sidecar is "local", but only one talking
    to SQLite is storing locally.
    """
    value = (residency or RESIDENCY_SERVER).strip().lower()
    if value not in RESIDENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown residency {residency!r}. Expected one of {', '.join(RESIDENCIES)}.",
        )
    if value == RESIDENCY_DEVICE and storage_location() != STORAGE_LOCAL:
        raise HTTPException(
            status_code=422,
            detail=(
                "This connection is marked device-only, but this Duct backend "
                "stores to a shared database. Save it from the desktop app "
                "running on its own local database, or store it to your account."
            ),
        )
    return value


def _refuse_server_only_keys(connector_type: str, credentials: dict) -> None:
    """A grant Duct verified itself is never taken from a request (service/github/app.py)."""
    reserved = server_only_keys_in(connector_type, credentials)
    if reserved:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{', '.join(reserved)} is set by Duct's own connect flow, never by a "
                "request. Use Connect on the Connections page."
            ),
        )


@router.post("", status_code=201)
def save_connector(
    body: ConnectorIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConnectorOut:
    if body.connector_type not in ALLOWED_CONNECTOR_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown connector type: {body.connector_type!r}")
    _refuse_server_only_keys(body.connector_type, body.credentials)

    residency = _check_residency(body.residency)
    # The same upsert the onboarding sign-in bundle writes through, so what a
    # reconnect keeps is decided in one place (service/connector_store.py).
    row = upsert_credential(
        session,
        user_id=user.id,
        connector_type=body.connector_type,
        credentials=body.credentials,
        granted_scopes=body.granted_scopes,
        account_id=body.account_id,
        account_name=body.account_name,
        residency=residency,
    )
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{connector_id}", status_code=204)
def delete_connector(
    connector_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    row = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.id == connector_id,
            ConnectorCredential.user_id == user.id,
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Connector not found")
    session.delete(row)
    session.commit()


# ---------------------------------------------------------------------------
# GitHub App: the one-click connection (service/github/app.py has the flow)
# ---------------------------------------------------------------------------

class GitHubClaimIn(BaseModel):
    code: str


@router.get("/github/app")
def github_app_status(user: User = Depends(get_current_user)) -> dict:
    """Whether this server can connect GitHub in one click, or only by token.

    Self-hosted installs have no App to offer, so the page asks before it
    draws a button that could only fail.
    """
    available = gh_app.is_configured()
    return {"available": available, "manage_url": gh_app.manage_url() if available else ""}


@router.post("/github/connect")
def start_github_connect(user: User = Depends(get_current_user)) -> dict:
    """A five-minute, single-use code naming the signed-in user.

    The authorize route is a browser navigation, which carries no bearer
    token, so this is how it learns whose connect it is — the guest-link
    pattern from sign-in, in its own namespace.
    """
    if not gh_app.is_configured():
        raise HTTPException(
            status_code=501,
            detail="The GitHub App is not configured on this server. Connect with a fine-grained token instead.",
        )
    return {"link": store_connect_link_code(str(user.id))}


@router.post("/github/claim")
def claim_github_grant(
    body: GitHubClaimIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Store what GitHub granted, as one row per repository, for the user who started it.

    The only writer of an App grant. The code came back through a redirect
    any browser could be sent to, so it is honoured for the user whose link
    code began the connect and for no one else. Someone else's code answers
    exactly as an unknown one does, and is spent either way.
    """
    payload = consume_github_grant(body.code.strip())
    if payload is None or payload.get("user_id") != str(user.id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="That GitHub connection expired or was started from another account. Connect again.",
        )
    grant = payload.get("grant") or {}
    rows = _store_github_grant(session, user.id, grant.get("repos") or [])
    session.commit()
    for row in rows:
        session.refresh(row)
    return {"connectors": [_to_out(r) for r in rows], "omitted": int(grant.get("omitted") or 0)}


def _store_github_grant(session: Session, user_id: UUID, repos: list[dict]) -> list[ConnectorCredential]:
    """Upsert a row per granted repository; drop App rows GitHub no longer grants.

    Rows the same shape a pasted token writes (``account_id`` = ``owner/name``),
    so the card, the project picker and FetchData need nothing new. A pasted
    token's row for a repository the App now covers is replaced by the App's;
    one for any other repository is the user's own and is left alone.
    """
    granted = {str(r.get("full_name") or "") for r in repos} - {""}
    existing = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user_id,
            ConnectorCredential.connector_type == GITHUB_CONNECTOR_ID,
        )
    ).scalars().all()
    for row in existing:
        if row.account_id in granted:
            continue
        try:
            stored = decrypt_credentials(row.credentials_enc)
        except Exception:  # noqa: BLE001 — an unreadable row is not provably an App grant
            continue
        if stored.get(gh_app.INSTALLATION_ID_KEY):
            session.delete(row)

    rows = []
    for repo in repos:
        full_name = str(repo.get("full_name") or "")
        installation_id = str(repo.get("installation_id") or "")
        if not full_name or not installation_id:
            continue
        rows.append(upsert_credential(
            session,
            user_id=user_id,
            connector_type=GITHUB_CONNECTOR_ID,
            credentials={gh_app.INSTALLATION_ID_KEY: installation_id, "repo": full_name},
            account_id=full_name,
            account_name=full_name,
        ))
    return rows
