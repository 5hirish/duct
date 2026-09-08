"""What Duct has spent on this user's key.

Read-only, and scoped to the caller by the query itself rather than by a check
beside it. Spending is the most personal data in the product under
bring-your-own-key — every row here is a charge on the caller's own provider
account — so ``summarise`` takes ``user_id`` as a required argument and there is
no code path that omits it.

``project_id`` narrows the window and is membership-checked the usual way: 404
for a non-member, never 403, so the response is not an oracle for which project
ids exist.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from db.session import get_session
from models.auth import User
from service.auth import get_current_user
from service.membership import get_project_for_user
from service.usage import DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS, summarise

router = APIRouter(tags=["usage"])


@router.get("")
def get_usage(
    project_id: UUID | None = None,
    window_days: int = Query(default=DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if project_id is not None:
        # 404 for non-members — never confirm a foreign project id exists.
        get_project_for_user(project_id, user, session)

    return summarise(
        user_id=user.id,
        project_id=project_id,
        window_days=window_days,
    ).as_dict()
