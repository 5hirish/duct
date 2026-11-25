"""Checking what a person allows an agent, before a token carries it.

One function for both doors, the consent page and the personal-token form,
so neither can grant something the other would refuse.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlmodel import Session

from models.auth import User
from service.mcp_server import scopes as mcp_scopes
from service.membership import accessible_projects


class GrantError(ValueError):
    """A grant the person has to change, in words the page can show."""


def check_grant(
    user: User,
    scopes: Iterable[str],
    project_ids: Iterable[UUID | str] | None,
    session: Session,
) -> tuple[str, list[str] | None]:
    """The scopes to store and the project ids, or ``GrantError``.

    Each project must be one the person can reach today: a grant naming any
    other would read as a promise the server then breaks, and an id that is
    not theirs must not be confirmable by trying it here.
    """
    granted = mcp_scopes.serialize(mcp_scopes.parse(list(scopes)))
    if project_ids is None:
        return granted, None
    chosen = {str(p) for p in project_ids}
    if not chosen:
        raise GrantError("Pick at least one project, or allow every project.")
    reachable = {str(p.id) for p in accessible_projects(user, session)}
    if not chosen <= reachable:
        raise GrantError("One of those projects is not yours to share. Pick from your projects.")
    return granted, sorted(chosen)
