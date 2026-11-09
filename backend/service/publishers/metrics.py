"""Every post a project's schedulers report, read once for every reader.

Two readers want the same fan-out: the Analytics tab's per-post table
(``routes/content.py``) and the insights agent's ``social_post_metrics``
entity (``agents/insights/fetchers.py``), which is how a growth report puts
the posting side next to search and traffic. Each used to be its own loop
over the connected schedulers, and two loops over paid vendor APIs drift in
the one way that matters: which failures stop the read.

Two rules, held here so both readers keep them. **One scheduler failing is
a notice, every scheduler failing is an error**: on 2026-11-08 a stale
PostBridge key hid a working Zernio behind "PostBridge didn't accept the
saved API key". And **the rows are scoped to the platforms the project
linked** (Content → Accounts) when it linked any: one scheduler key can hold
several brands' accounts, and the project's links are what say which posts
are this project's. The route applied that scope and the agent's entity did
not, until the scope moved here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlmodel import Session

from sqlalchemy import select

from models.content.social_link import ContentSocialLink
from models.project import Project
from service.publishers.base import PublisherError, PublisherSpec, ReportedPost
from service.publishers.registry import connected_specs, publisher_for
from service.vendor_keys import VendorNotConnected


@dataclass(frozen=True)
class ReportedPosts:
    """What the project's schedulers said, and which of them did not answer."""

    rows: list[tuple[PublisherSpec, ReportedPost]] = field(default_factory=list)
    failures: list[tuple[PublisherSpec, Exception]] = field(default_factory=list)
    asked: list[PublisherSpec] = field(default_factory=list)

    @property
    def all_failed(self) -> bool:
        return bool(self.asked) and len(self.failures) == len(self.asked)


async def collect_reported_posts(
    db: Session, proj: Project, *, refresh: bool = False,
    specs: list[PublisherSpec] | None = None,
) -> ReportedPosts:
    """Ask every scheduler the project's owner connected for the posts it
    reports numbers on, or only ``specs`` when the caller has already decided
    which schedulers this project uses (the Analytics tab does, so a stale
    key on a scheduler the project left cannot hide the one it posts
    through). Never raises for a scheduler that fails; the caller reads
    ``failures`` and decides whether none answering is its error."""
    asked = list(specs) if specs is not None else connected_specs(proj.user_id, db)
    linked = _linked_platforms(db, proj.id)
    out = ReportedPosts(asked=asked)
    for spec in asked:
        try:
            pub = publisher_for(proj.user_id, spec.id, db)
            async with pub:
                out.rows.extend(
                    (spec, r)
                    for r in await pub.reported_posts(refresh=refresh)
                    if not linked or r.platform in linked
                )
        except (PublisherError, VendorNotConnected) as exc:
            out.failures.append((spec, exc))
    return out


def _linked_platforms(db: Session, project_id: UUID) -> set[str]:
    """The platforms this project linked accounts on; empty means "show all",
    the Accounts tab's own reading. Read here rather than through
    ``agents/content/publishing.linked_accounts`` because a service module
    importing from ``agents/`` is the layering this tree avoids."""
    rows = db.execute(
        select(ContentSocialLink.platform).where(ContentSocialLink.project_id == project_id)
    ).scalars().all()
    return {p for p in rows if p}


def as_rows(result: ReportedPosts) -> list[dict]:
    """The reported posts as plain rows, the shape the agent's catalog
    declares (``agents/insights/catalog/publishers.py``)."""
    return [
        {
            "publisher": spec.id,
            "platform": r.platform,
            "title": r.title,
            "url": r.url,
            "views": r.views,
            "likes": r.likes,
            "comments": r.comments,
            "shares": r.shares,
            # Declared in the catalog so Duct sums it and the rate is a ratio
            # of totals (agents/insights/totals.py), never a mean of rates.
            "engagement": r.likes + r.comments + r.shares,
            "posted_at": r.posted_at or "",
        }
        for spec, r in result.rows
    ]


def owner_has_scheduler(db: Session, owner_id: UUID) -> bool:
    return bool(connected_specs(owner_id, db))


__all__ = ["ReportedPosts", "as_rows", "collect_reported_posts", "owner_has_scheduler"]
