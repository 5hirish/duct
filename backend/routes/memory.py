"""Project memory endpoints — /api/user/projects/{id}/memory (Bearer JWT).

The read side of the timeline (`/project/[projectId]/memory`) and the user's
controls over it: remember something by hand, confirm or correct what an agent
proposed, pin it, archive it, delete it.

Every route is membership-checked through ``service.membership`` — project
isolation is absolute, and a non-member gets 404 rather than 403 so a foreign
project id is never confirmed to exist.

Superseded entries are returned by default (``include_superseded``): the point
of the timeline is that "we thought X, then learned Y" reads as history, not as
an error. The digest the agent sees is the filtered view; this is the archive.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_404_NOT_FOUND

from db.session import get_session
from models.auth import User
from models.memory import (
    MEMORY_KINDS,
    SCOPE_USER,
    canonical_kind,
    SOURCE_USER,
    STATUS_ARCHIVED,
    STATUS_CONFIRMED,
    STATUS_SUPERSEDED,
    USER_KINDS,
    ProjectMemory,
)
from service.auth import get_current_user, get_user_provider_keys
from service.membership import get_project_for_user
from service.memory import remember, search, short_id
from utils.dates import parse_iso, utcnow

router = APIRouter(tags=["memory"])

_MAX_LIMIT = 200


def _serialize(row: ProjectMemory) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "short_id": short_id(row.id),
        "scope": row.scope,
        # On a private row: the one project it applies to, or None for all.
        "project_id": str(row.project_id) if row.project_id else None,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "entity_key": row.entity_key,
        "attribute": row.attribute,
        "period": row.period,
        "value": row.value or {},
        "observed_at": row.observed_at.isoformat() if row.observed_at else "",
        "valid_from": row.valid_from.isoformat() if row.valid_from else "",
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "recorded_at": row.recorded_at.isoformat() if row.recorded_at else "",
        "superseded_by": short_id(row.superseded_by) if row.superseded_by else None,
        "source_type": row.source_type,
        "source_refs": row.source_refs or [],
        "agent_type": row.agent_type,
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "confidence": row.confidence,
        "importance": row.importance,
        "status": row.status,
        "pinned": row.pinned,
        "recall_count": row.recall_count,
        "last_recalled_at": row.last_recalled_at.isoformat() if row.last_recalled_at else None,
        "meta": row.meta or {},
    }


def _serialize_list(session: Session, rows: list[ProjectMemory]) -> list[dict[str, Any]]:
    """Rows for the page, each current one saying what it replaced.

    "Target CPA $45" is easier to trust as "was $60 until 30 Jun" than as two
    rows and a toggle, so the previous version rides on the current one. The
    previous rows are looked up by ``superseded_by`` within the same owner,
    since a row id alone is not a boundary.
    """
    out = [_serialize(r) for r in rows]
    current = [r for r in rows if r.status != STATUS_SUPERSEDED]
    if not current:
        return out
    stmt = select(ProjectMemory).where(
        ProjectMemory.superseded_by.in_([r.id for r in current])
    )
    first = current[0]
    if first.scope == SCOPE_USER:
        stmt = stmt.where(ProjectMemory.user_id == first.user_id, ProjectMemory.scope == SCOPE_USER)
    else:
        stmt = stmt.where(ProjectMemory.project_id == first.project_id, ProjectMemory.scope != SCOPE_USER)
    previous: dict[UUID, ProjectMemory] = {}
    for row in session.execute(stmt).scalars():
        kept = previous.get(row.superseded_by)
        if kept is None or (row.valid_to and kept.valid_to and row.valid_to > kept.valid_to):
            previous[row.superseded_by] = row
    for item, row in zip(out, rows):
        prior = previous.get(row.id)
        if prior is not None:
            item["replaced"] = {
                "title": prior.title,
                "until": prior.valid_to.isoformat() if prior.valid_to else None,
            }
    return out


class MemoryIn(BaseModel):
    """A memory the user writes by hand ("Remember this")."""

    kind: str
    title: str
    body: str = ""
    scope: str = "project"
    entity_key: str = ""
    attribute: str = ""
    period: str = ""
    value: dict = Field(default_factory=dict)
    observed_at: str = ""
    importance: int = 5
    source_refs: list[dict] = Field(default_factory=list)
    # Private memory only: bind the entry to this project ("for this client,
    # brief me in Spanish"). Empty means it holds on every project.
    project_id: str = ""


class MemoryPatch(BaseModel):
    """The user's verdict on an entry. Every field is optional."""

    title: str | None = None
    body: str | None = None
    status: str | None = None   # 'confirmed' | 'archived'
    pinned: bool | None = None
    importance: int | None = None


class MemoryMove(BaseModel):
    """Where a private entry applies: one project, or every project ("")."""

    project_id: str = ""


def _private_binding(session: Session, user: User, raw: str) -> UUID | None:
    """The project a private entry is bound to, checked: a member's own, or 404."""
    if not raw:
        return None
    try:
        project_id = UUID(raw)
    except ValueError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Project not found") from None
    get_project_for_user(project_id, user, session)
    return project_id


def _get_owned(session: Session, user: User, project_id: UUID, memory_id: UUID) -> ProjectMemory:
    get_project_for_user(project_id, user, session)
    row = session.get(ProjectMemory, memory_id)
    # Private rows 404 here whatever their project id: the project routes
    # are for what every member may see.
    if row is None or row.project_id != project_id or row.scope == SCOPE_USER:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Memory not found")
    return row


@router.get("/{project_id}/memory")
def list_memory(
    project_id: UUID,
    q: str = "",
    kind: str = "",
    entity: str = "",
    status: str = "",
    scope: str = "",
    from_date: str = "",
    to_date: str = "",
    include_superseded: bool = True,
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """The project timeline: entries newest first, with the filter set the UI offers."""
    project = get_project_for_user(project_id, user, session)
    rows = search(
        session,
        project_id=project_id,
        query=q,
        kinds=[k.strip() for k in kind.split(",") if k.strip()] or None,
        entity=entity,
        scope=scope or None,
        since=parse_iso(from_date),
        until=parse_iso(to_date),
        statuses=[s.strip() for s in status.split(",") if s.strip()] or None,
        include_superseded=include_superseded,
        limit=limit,
    )
    return {
        "items": _serialize_list(session, rows),
        # Kinds actually present, so the UI's filter chips reflect this project
        # rather than the full vocabulary.
        "kinds": sorted({r.kind for r in rows}),
        # The pause switch reads its state from here, exactly as the user scope
        # does. Without it the control renders unchecked on every reload and
        # tells the user memory is on while it is off.
        "memory_paused": bool(project.memory_paused),
    }


@router.post("/{project_id}/memory", status_code=201)
def create_memory(
    project_id: UUID,
    body: MemoryIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """"Remember this" — a user statement, which lands confirmed, not proposed."""
    get_project_for_user(project_id, user, session)
    kind = canonical_kind(body.kind)
    if kind not in MEMORY_KINDS:
        raise HTTPException(status_code=422, detail=f"Unknown memory kind: {body.kind!r}")
    scope = SCOPE_USER if body.scope == SCOPE_USER else "project"
    row = remember(
        session,
        scope=scope,
        kind=kind,
        title=body.title,
        body=body.body,
        project_id=None if scope == SCOPE_USER else project_id,
        user_id=user.id,
        entity_key=body.entity_key,
        attribute=body.attribute,
        period=body.period,
        value=body.value,
        observed_at=parse_iso(body.observed_at),
        source_type=SOURCE_USER,
        source_refs=body.source_refs or [{"source": "user"}],
        confidence="high",
        importance=body.importance,
        status=STATUS_CONFIRMED,
    )
    if row is None:
        raise HTTPException(status_code=422, detail="Memory rejected — a kind and title are required.")
    return _serialize(row)


def _apply_patch(session: Session, row: ProjectMemory, body: MemoryPatch, user: User) -> ProjectMemory:
    """Apply the user's verdict to one entry, in either scope.

    A user edit on a proposed entry confirms it — the user overrides the agent,
    and the entry stops being a proposal the moment a human touches its content.
    """
    edited = False
    if body.title is not None and body.title.strip():
        row.title = body.title.strip()[:200]
        edited = True
    if body.body is not None:
        row.body = body.body[:2000]
        edited = True
    if body.status is not None:
        if body.status not in (STATUS_CONFIRMED, STATUS_ARCHIVED):
            raise HTTPException(
                status_code=422,
                detail="status must be 'confirmed' or 'archived' — supersession is automatic.",
            )
        row.status = body.status
    elif edited:
        row.status = STATUS_CONFIRMED
    if body.pinned is not None:
        row.pinned = bool(body.pinned)
    if body.importance is not None:
        row.importance = max(0, min(int(body.importance), 10))
    if edited:
        row.source_type = SOURCE_USER
        refs = list(row.source_refs or [])
        refs.append({"edited_by": str(user.id)})
        row.source_refs = refs[:20]

    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.patch("/{project_id}/memory/{memory_id}")
def update_memory(
    project_id: UUID,
    memory_id: UUID,
    body: MemoryPatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Confirm, correct, pin or archive one entry."""
    row = _get_owned(session, user, project_id, memory_id)
    return _serialize(_apply_patch(session, row, body, user))


@router.delete("/{project_id}/memory/{memory_id}", status_code=204)
def delete_memory(
    project_id: UUID,
    memory_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Delete one entry outright.

    The *system* never deletes — it closes or archives. This route exists so the
    user can, which is the difference between memory they control and memory
    that happens to them.
    """
    row = _get_owned(session, user, project_id, memory_id)
    closed = list(
        session.execute(
            select(ProjectMemory).where(ProjectMemory.superseded_by == row.id)
        ).scalars()
    )
    # Delete first, then reopen: while both rows are active they share a state
    # key, and the partial unique index (rightly) refuses that.
    session.delete(row)
    session.flush()
    # Anything this entry closed goes back to being current, so a delete cannot
    # leave the timeline with a state key that has no active row.
    for prior in closed:
        prior.superseded_by = None
        prior.valid_to = None
        prior.status = STATUS_CONFIRMED
        session.add(prior)
    session.commit()


# ---------------------------------------------------------------------------
# Controls — pause, reset, export
#
# The three verbs that make memory something the user owns rather than
# something that happens to them. Every assistant that shipped memory well
# offers all three; the ones that shipped only "delete one" got written about.
# ---------------------------------------------------------------------------

class PauseIn(BaseModel):
    paused: bool


@router.post("/{project_id}/memory/pause")
def set_pause(
    project_id: UUID,
    body: PauseIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Stop (or resume) remembering anything new about this project.

    Reads are deliberately unaffected: pausing means "stop learning", not
    "forget what you know". Reset and delete are the other verb.
    """
    project = get_project_for_user(project_id, user, session)
    project.memory_paused = bool(body.paused)
    session.add(project)
    session.commit()
    return {"project_id": str(project_id), "memory_paused": project.memory_paused}


@router.post("/{project_id}/memory/reset")
def reset_memory(
    project_id: UUID,
    confirm: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Delete every memory for this project. Irreversible, so `confirm` is required.

    Export first if you want a copy — this is the one operation that does not
    leave history behind.
    """
    get_project_for_user(project_id, user, session)
    if not confirm:
        raise HTTPException(
            status_code=422,
            detail="Reset deletes every memory for this project. Retry with confirm=true.",
        )
    deleted = session.execute(
        sa.delete(ProjectMemory).where(
            ProjectMemory.project_id == project_id, ProjectMemory.scope != SCOPE_USER
        )
    ).rowcount
    session.commit()
    return {"deleted": int(deleted or 0)}


@router.get("/{project_id}/memory/export")
def export_memory(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Everything, superseded and archived included, as portable JSON."""
    get_project_for_user(project_id, user, session)
    rows = session.execute(
        select(ProjectMemory)
        .where(ProjectMemory.project_id == project_id, ProjectMemory.scope != SCOPE_USER)
        .order_by(ProjectMemory.observed_at)
    ).scalars()
    return {
        "project_id": str(project_id),
        "exported_at": utcnow().isoformat(),
        "memories": [_serialize(r) for r in rows],
    }


# Declared after /memory/export on purpose: FastAPI matches in declaration
# order, and a {memory_id} path parameter would otherwise swallow "export".
@router.get("/{project_id}/memory/{memory_id}")
def get_one(
    project_id: UUID,
    memory_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """One entry in full — the drawer behind a chip."""
    return _serialize(_get_owned(session, user, project_id, memory_id))


# ---------------------------------------------------------------------------
# User scope — /api/user/memory
#
# What Duct knows about the person rather than the account: how they want
# analysis done, what they read, what they ignore. Crosses projects, private to
# them, and governed by its own pause switch.
# ---------------------------------------------------------------------------

user_router = APIRouter(tags=["memory"])


@user_router.get("")
def list_user_memory(
    q: str = "",
    kind: str = "",
    project_id: str = "",
    status: str = "",
    from_date: str = "",
    to_date: str = "",
    include_superseded: bool = True,
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """The caller's own memory. Only ever theirs: no role, owner or project
    membership reaches another person's rows, because the query is keyed on
    the signed-in user and nothing in the request can change that.

    ``project_id`` adds what is private to that project to what holds
    everywhere; without it, only what holds everywhere."""
    bound = _private_binding(session, user, project_id)
    rows = search(
        session,
        user_id=user.id,
        project_id=bound,
        scope=SCOPE_USER,
        query=q,
        kinds=[k.strip() for k in kind.split(",") if k.strip()] or None,
        since=parse_iso(from_date),
        until=parse_iso(to_date),
        statuses=[s.strip() for s in status.split(",") if s.strip()] or None,
        include_superseded=include_superseded,
        limit=limit,
    )
    return {
        "items": _serialize_list(session, rows),
        "kinds": sorted({r.kind for r in rows}),
        "memory_paused": bool(user.memory_paused),
    }


@user_router.post("", status_code=201)
def create_user_memory(
    body: MemoryIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    kind = canonical_kind(body.kind)
    if kind not in USER_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"User memory kinds are: {', '.join(sorted(USER_KINDS))}.",
        )
    bound = _private_binding(session, user, body.project_id)
    row = remember(
        session,
        scope=SCOPE_USER,
        kind=kind,
        title=body.title,
        body=body.body,
        user_id=user.id,
        project_id=bound,
        private_to_project=bound is not None,
        entity_key=body.entity_key,
        attribute=body.attribute,
        source_type=SOURCE_USER,
        source_refs=body.source_refs or [{"source": "user"}],
        confidence="high",
        importance=body.importance,
        status=STATUS_CONFIRMED,
    )
    if row is None:
        raise HTTPException(status_code=422, detail="Memory rejected — a kind and title are required.")
    return _serialize(row)


def _get_user_owned(session: Session, user: User, memory_id: UUID) -> ProjectMemory:
    row = session.get(ProjectMemory, memory_id)
    if row is None or row.scope != SCOPE_USER or row.user_id != user.id:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Memory not found")
    return row


@user_router.patch("/{memory_id}")
def update_user_memory(
    memory_id: UUID,
    body: MemoryPatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = _get_user_owned(session, user, memory_id)
    return _serialize(_apply_patch(session, row, body, user))


@user_router.post("/{memory_id}/move")
def move_user_memory(
    memory_id: UUID,
    body: MemoryMove,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Make a private entry hold on one project, or on every project.

    Written again under the new binding and the old row removed, because the
    binding is part of what the entry replaces and is replaced by: moving it
    in place would leave its dedupe and state keys pointing at the old one.
    """
    row = _get_user_owned(session, user, memory_id)
    bound = _private_binding(session, user, body.project_id)
    if row.project_id == bound:
        return _serialize(row)
    moved = remember(
        session,
        scope=SCOPE_USER,
        kind=row.kind,
        title=row.title,
        body=row.body,
        user_id=user.id,
        project_id=bound,
        private_to_project=bound is not None,
        entity_key=row.entity_key,
        attribute=row.attribute,
        period=row.period,
        value=row.value or {},
        observed_at=row.observed_at,
        source_type=SOURCE_USER,
        source_refs=list(row.source_refs or []) or [{"source": "user"}],
        confidence=row.confidence,
        importance=row.importance,
        status=STATUS_CONFIRMED,
        meta=row.meta or {},
    )
    if moved is None:
        raise HTTPException(status_code=422, detail="Could not move that memory.")
    if moved.id != row.id:
        session.delete(row)
        session.commit()
    return _serialize(moved)


@user_router.delete("/{memory_id}", status_code=204)
def delete_user_memory(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    session.delete(_get_user_owned(session, user, memory_id))
    session.commit()


@user_router.post("/catch-up", status_code=202)
async def catch_up_memory(
    user: User = Depends(get_current_user),
    user_keys: dict = Depends(get_user_provider_keys),
) -> dict:
    """Consolidate this owner's idle conversations on the keys in this request.

    The desktop app calls it when it opens and every half hour while it stays
    open: its keys live in the OS keychain, so this is the only time the
    background pass can spend them (``service/memory_consolidation.catch_up``).
    Scoped to projects the caller owns, since the owner pays for background
    work. Returns at once; the pass runs behind the response.
    """
    from service.memory_consolidation import schedule_catch_up

    return {"scheduled": schedule_catch_up(user.id, user_keys)}


@user_router.post("/pause")
def set_user_pause(
    body: PauseIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Stop inferring anything new about how this person works."""
    user.memory_paused = bool(body.paused)
    session.add(user)
    session.commit()
    return {"memory_paused": user.memory_paused}


@user_router.post("/reset")
def reset_user_memory(
    confirm: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if not confirm:
        raise HTTPException(
            status_code=422,
            detail="Reset deletes everything Duct has learned about you. Retry with confirm=true.",
        )
    deleted = session.execute(
        sa.delete(ProjectMemory).where(
            ProjectMemory.user_id == user.id, ProjectMemory.scope == SCOPE_USER
        )
    ).rowcount
    session.commit()
    return {"deleted": int(deleted or 0)}


@user_router.get("/export")
def export_user_memory(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.execute(
        select(ProjectMemory)
        .where(ProjectMemory.user_id == user.id, ProjectMemory.scope == SCOPE_USER)
        .order_by(ProjectMemory.observed_at)
    ).scalars()
    return {"exported_at": utcnow().isoformat(), "memories": [_serialize(r) for r in rows]}
