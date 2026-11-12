"""The read credentials of the repository a project has bound, for callers
outside FetchData: the on-release check (#563) and the star milestones (#564).

FetchData resolves the same thing inside ``fetch_entity``; this is that rule
for a single request, so neither caller grows its own copy.
"""

from __future__ import annotations

from uuid import UUID

from service.github import GITHUB_CONNECTOR_ID


def bound_read_credentials(user_id: UUID | None, project_id: UUID | None) -> dict | None:
    """The credential blob with ``repo`` set to the bound repository, or None
    when this project has no repository bound or nothing is stored for it."""
    if user_id is None or project_id is None:
        return None
    from db.session import get_session as db_session
    from service.connector_access import STATUS_BOUND, get_data_source, resolve_read_credentials

    with next(db_session()) as db:
        source = get_data_source(db, GITHUB_CONNECTOR_ID, user_id=user_id, project_id=project_id)
        if source is None or source.status != STATUS_BOUND or not source.account_id:
            return None
        creds = resolve_read_credentials(
            db, user_id=user_id, project_id=project_id, connector_type=GITHUB_CONNECTOR_ID,
            account_id=source.account_id,
        )
    return {**creds, "repo": source.account_id} if creds else None
