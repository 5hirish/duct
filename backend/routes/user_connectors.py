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
    join_scopes,
    missing_scopes,
    parse_scopes,
    scope_rows,
    scope_status,
)
from service.connectors import CAP_ACCOUNTS, ConnectorAuthContext, get_connector, registry
from service.credentials import decrypt_credentials, encrypt_credentials
from service.provider_keys import CONNECTOR_TYPE as PROVIDER_KEY_TYPE

router = APIRouter(tags=["user-connectors"])

ALLOWED_CONNECTOR_TYPES = {
    "google_ads", "ga4", "gsc", "gtm",
    # Manual-credential connectors (Phase 7) — Fernet JSON blobs fit any shape.
    "apple_ads", "meta_ads", "stripe", "revenuecat", "openai_ads",
    # Gads wave 2 — the cross-check + behaviour sources.
    "mixpanel", "clarity", "growthbook",
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


@router.post("", status_code=201)
def save_connector(
    body: ConnectorIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConnectorOut:
    if body.connector_type not in ALLOWED_CONNECTOR_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown connector type: {body.connector_type!r}")

    account_id = body.account_id.strip()
    residency = _check_residency(body.residency)

    # Upsert by (user_id, connector_type, account_id)
    existing = session.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user.id,
            ConnectorCredential.connector_type == body.connector_type,
            ConnectorCredential.account_id == account_id,
        )
    ).scalars().first()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    enc = encrypt_credentials(body.credentials)

    granted = join_scopes(parse_scopes(body.granted_scopes))

    if existing:
        existing.account_name = body.account_name
        existing.credentials_enc = enc
        existing.residency = residency
        # Only overwrite when this save actually carries a grant. A later save
        # that does not know the scopes (an account rename, a manual re-save)
        # must not erase what the OAuth round-trip recorded.
        if granted:
            existing.granted_scopes = granted
        existing.updated_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return _to_out(existing)

    row = ConnectorCredential(
        user_id=user.id,
        connector_type=body.connector_type,
        account_id=account_id,
        account_name=body.account_name,
        credentials_enc=enc,
        granted_scopes=granted,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
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
