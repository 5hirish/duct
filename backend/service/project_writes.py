"""Writing a project row: the upsert, the lock, and the draft merge around it.

An agent's edit (``apply_edit``) and its undo (``undo_edit``) land here too,
beside the draft, so the lock and the write path are shared.

Two callers write drafts, and they must not drift: the app's
``POST /api/user/projects/{id}/draft`` and the MCP server's ``draft_project``
tool, which is an outside agent writing on the person's behalf. Both land here,
so the rules in ``service/project_draft.py`` are applied the same way whoever
writes, and a project created either way gets its owner row and its seeded
memory.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from models.auth import User
from models.project import Project, unique_slug
from service.membership import ensure_owner_membership, get_project_for_user
from service.memory import seed_project_profile
from service.project_draft import UNTITLED_PROJECT, edit_fields, is_blank, merge_draft, revert_fields
from utils.dates import utcnow


def project_for_write(
    project_id: UUID, user: User, session: Session, *, name: str, slug_name: str | None = None
) -> tuple[Project, bool]:
    """The project a write lands on, locked, or a new one owned by the caller.

    The frontend generates project UUIDs locally (and already references them
    from content plans / agent contexts), so a missing project is created with
    the supplied id rather than 404'd, keeping those references valid. The row
    is locked for the rest of the transaction: two drafts arriving together
    each read the project, merge, and write it back, and without the lock the
    second write drops the first one's fields.
    """
    existing = session.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    ).scalars().first()
    if existing is None:
        project = Project(
            id=project_id,
            user_id=user.id,
            name=name,
            slug=unique_slug(session, user.id, slug_name or name),
        )
        session.add(project)
        return project, True
    # Raises 404 when the caller is neither owner nor collaborator, so an
    # unrelated project can never be overwritten through an upsert.
    return get_project_for_user(project_id, user, session), False


def finish_write(project: Project, is_new: bool, user: User, session: Session) -> Project:
    session.add(project)
    if is_new:
        # Flush after the NOT NULL columns are populated, so the owner row can
        # reference a project that actually exists.
        session.flush()
        ensure_owner_membership(project, session)
    session.commit()
    session.refresh(project)
    # A changed target supersedes the previous one rather than overwriting it —
    # that is what makes "target CPA $45 (was $60 until 30 Jun)" possible.
    seed_project_profile(session, project, user_id=user.id)
    return project


def apply_draft(
    project_id: UUID,
    fields: dict[str, dict[str, Any]],
    user: User,
    session: Session,
) -> tuple[Project, list[str], bool]:
    """Merge a draft (``{name: {value, provenance}}``) into the project.

    Returns the project, the fields that landed, and whether it was created.
    A new project starts untitled so the drafted name lands as a draft, with
    its label, and a better one from a later draft can still replace it. The
    slug is the one place the drafted name is used up front: nothing rewrites
    a slug after creation, and the content agent reads it. A draft that
    changes nothing leaves ``updated_at`` alone, so it never makes the
    server's copy look newer than a device's for no reason.
    """
    drafted = (fields.get("name") or {}).get("value")
    slug_name = drafted if not is_blank("name", drafted) else None
    project, is_new = project_for_write(
        project_id, user, session, name=UNTITLED_PROJECT, slug_name=slug_name
    )
    landed = merge_draft(project, fields)
    if landed or is_new:
        project.updated_at = utcnow()
    return finish_write(project, is_new, user, session), landed, is_new


# The activity actions an agent's edit and its undo are recorded under. The MCP
# tool writes the first, the undo route finds edits by it and writes the second,
# and the app's activity feed reads both, so they are a contract, not labels.
ACTION_EDITED = "project.edited"
ACTION_EDIT_UNDONE = "project.edit_undone"


def _locked_member_project(project_id: UUID, user: User, session: Session) -> Project:
    """The project, locked, when the caller may write it; 404 otherwise. An
    edit never creates a project: there is nothing to edit yet."""
    found = session.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    ).scalars().first()
    if found is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Project not found")
    return get_project_for_user(project_id, user, session)


def apply_edit(
    project_id: UUID, values: dict[str, Any], user: User, session: Session
) -> tuple[Project, list[str], dict[str, Any], dict[str, str | None]]:
    """Set fields as the person asked, keeping what they replaced.

    Returns the project, the fields that changed, and the replaced values and
    labels, which the caller records so ``undo_edit`` can put them back.
    """
    project = _locked_member_project(project_id, user, session)
    changed, before, before_labels = edit_fields(project, values)
    if changed:
        project.updated_at = utcnow()
    return finish_write(project, False, user, session), changed, before, before_labels


def undo_edit(
    project_id: UUID, edit: dict[str, Any], user: User, session: Session
) -> tuple[Project, list[str], list[str]]:
    """Put back what one recorded edit replaced. ``edit`` is the activity
    row's data: ``after``, ``before`` and ``before_labels``."""
    project = _locked_member_project(project_id, user, session)
    restored, skipped = revert_fields(
        project, edit.get("after") or {}, edit.get("before") or {}, edit.get("before_labels") or {}
    )
    if restored:
        project.updated_at = utcnow()
    return finish_write(project, False, user, session), restored, skipped
