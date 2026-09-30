"""What Duct remembers about a project's linked PostBridge accounts.

The accounts themselves live at PostBridge; ``content_social_links`` records
which of them a project posts to. The one fact kept beside each is X Premium,
because it moves X's character limit from 280 to 25,000 and the drafting
prompt, the review and the preview all need the limit without a network call.
It is only as fresh as the last account listing, which is why every listing
writes it back (``remember_account_state``). Publishing re-reads the live
accounts anyway, so a stale flag can cost a draft its length, never a post.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlmodel import Session, select

from models.content import ContentSocialLink
from utils.dates import utcnow

_X = "twitter"


def project_x_premium(db: Session, project_id: UUID) -> bool:
    """True when the project posts to X and every linked X account has
    Premium. One standard account holds the whole project to 280, since a
    draft is written once and goes to all of them."""
    flags = db.exec(
        select(ContentSocialLink.has_x_premium)
        .where(ContentSocialLink.project_id == project_id, ContentSocialLink.platform == _X)
    ).all()
    return bool(flags) and all(flags)


def remember_account_state(db: Session, project_id: UUID, accounts: Iterable) -> None:
    """Write PostBridge's current Premium flag onto the project's linked rows.
    ``accounts`` are ``PostBridgeSocialAccount``; unlinked ones are ignored."""
    premium = {str(a.id): bool(a.has_x_premium) for a in accounts}
    rows = db.exec(select(ContentSocialLink).where(ContentSocialLink.project_id == project_id)).all()
    changed = False
    for row in rows:
        flag = premium.get(row.external_account_id)
        if flag is not None and flag != row.has_x_premium:
            row.has_x_premium = flag
            row.updated_at = utcnow()
            db.add(row)
            changed = True
    if changed:
        db.commit()
