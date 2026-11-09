"""Every post a project's schedulers report, read once for every reader.

Two readers want the same fan-out: the Analytics tab's per-post table
(``routes/content.py``) and the insights agent's ``social_post_metrics``
entity (``agents/insights/fetchers.py``), which is how a growth report puts
the posting side next to search and traffic. Each used to be its own loop
over the connected schedulers, and two loops over paid vendor APIs drift in
the one way that matters: which failures stop the read.

The rule, held here: **one scheduler failing is a notice, every scheduler
failing is an error.** On 2026-11-08 a stale PostBridge key hid a working
Zernio behind "PostBridge didn't accept the saved API key".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlmodel import Session

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
    db: Session, proj: Project, *, refresh: bool = False
) -> ReportedPosts:
    """Ask every scheduler the project's owner connected for the posts it
    reports numbers on. Never raises for a scheduler that fails; the caller
    reads ``failures`` and decides whether none answering is its error."""
    asked = connected_specs(proj.user_id, db)
    out = ReportedPosts(asked=asked)
    for spec in asked:
        try:
            pub = publisher_for(proj.user_id, spec.id, db)
            async with pub:
                out.rows.extend((spec, r) for r in await pub.reported_posts(refresh=refresh))
        except (PublisherError, VendorNotConnected) as exc:
            out.failures.append((spec, exc))
    return out


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
