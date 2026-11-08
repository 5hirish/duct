"""What Duct asks of a social scheduler, in Duct's words.

A scheduler (PostBridge, Zernio) is a connector the person brings: it holds
their social accounts, takes a post and its pictures, publishes it now or at
a time, and reports what it did and how it is doing. Each one says all of
that in its own vocabulary — PostBridge's numeric account ids and ``posted``,
Zernio's ObjectIds and ``published`` — and Content Studio used to speak
PostBridge's directly, so a second scheduler would have meant a second copy
of every publish path. This module is the one vocabulary they are translated
into, and the only one ``agents/content/publishing.py``, the routes and the
agent's tools read.

An adapter wraps one vendor's client (``service/post_bridge/publisher.py``,
``service/zernio/publisher.py``) and raises ``PublisherError`` for every way
the vendor can fail, so no caller catches a vendor exception. What a
scheduler can and cannot do differs, and is data on its ``PublisherSpec``
rather than a branch at a call site: which platforms it reports numbers for,
how many of a post's replies it publishes, whether it strips links on X.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from service.vendor_keys import VendorKey


class RemoteStatus(StrEnum):
    """Where a post stands at its scheduler. ``publishing`` is a post going
    out as we ask, and ``partial`` one that reached some accounts and not
    others: both count as out, because nothing changed in Duct reaches them."""

    DRAFT      = "draft"
    SCHEDULED  = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED  = "published"
    PARTIAL    = "partial"
    FAILED     = "failed"
    CANCELLED  = "cancelled"

    @property
    def is_out(self) -> bool:
        return self in (RemoteStatus.PUBLISHING, RemoteStatus.PUBLISHED, RemoteStatus.PARTIAL)


class PublisherError(Exception):
    """A scheduler refused, failed or could not be reached. ``status_code`` is
    the vendor's HTTP status, 0 when it never answered; ``message`` is its own
    words, for a person or the model to act on."""

    def __init__(self, message: str, *, status_code: int = 0, code: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code

    @property
    def key_rejected(self) -> bool:
        return self.status_code in (401, 403)

    @property
    def not_found(self) -> bool:
        return self.status_code == 404


class PostAlreadyOut(Exception):
    """The scheduler has published the post, or is publishing it: nothing
    changed in Duct can reach it any more."""


@dataclass(frozen=True)
class SocialAccount:
    """One account the person connected at their scheduler. ``platform`` is
    Duct's channel id (``agents.content.channels.Platform``), never the
    vendor's spelling."""

    id: str
    platform: str
    username: str
    display_name: str = ""
    avatar_url: str = ""
    needs_reconnect: bool = False


@dataclass(frozen=True)
class MediaRef:
    """A file the scheduler holds, as the post that uses it must name it."""

    id: str
    mime_type: str


@dataclass(frozen=True)
class Target:
    """One account a post goes to. ``platform`` may be "" where the caller
    does not know it; an adapter that needs it looks it up."""

    account_id: str
    platform: str = ""


@dataclass(frozen=True)
class Outgoing:
    """A post on its way to a scheduler: its words, the author's replies (the
    adapter publishes as many as its spec says), its media in order, and when."""

    caption: str
    targets: tuple[Target, ...]
    replies: tuple[str, ...] = ()
    media: tuple[MediaRef, ...] = ()
    scheduled_at: datetime | None = None
    tiktok_draft: bool = False


@dataclass(frozen=True)
class Delivery:
    """What became of the post on one account. ``ok`` is None while it has
    not gone out yet."""

    account_id: str
    platform: str = ""
    ok: bool | None = None
    url: str = ""
    error: str = ""


@dataclass(frozen=True)
class RemotePost:
    id: str
    status: RemoteStatus
    scheduled_at: datetime | None = None
    deliveries: tuple[Delivery, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return next((d.url for d in self.deliveries if d.ok and d.url), "")

    @property
    def failure_reason(self) -> str:
        """The scheduler's own words for why the post did not go out, or ""
        when it gave none: its warnings, else what each account's attempt said."""
        words = [w for w in self.warnings if w] or [d.error for d in self.deliveries if d.ok is False]
        return " ".join(dict.fromkeys(w.strip() for w in words if w and w.strip()))


@dataclass(frozen=True)
class PostMetrics:
    """A post's numbers as the scheduler reports them. ``values`` holds perf
    keys ``service/content_metrics.METRIC_ALIASES`` knows, plus whatever else
    is worth keeping (the platform's link, the cover); ``ref`` is the
    scheduler's handle for these numbers, kept on the row so the next pull
    skips the lookup."""

    ref: str
    values: Mapping[str, Any]
    synced_at: str | None = None
    daily: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class ReportedPost:
    """One row of the Analytics tab: a post on a connected account, whoever
    published it. ``remote_post_id`` ties it to a Duct post that went out
    through this scheduler, when the scheduler knows the link."""

    ref: str
    platform: str
    remote_post_id: str = ""
    title: str = ""
    url: str = ""
    cover_url: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    posted_at: str | None = None
    synced_at: str | None = None


@dataclass(frozen=True)
class PublisherSpec:
    """A scheduler as Duct knows it: its name, the key a person brings for it,
    and what it can do. Every capability is per platform, because that is how
    the vendors differ.

    ``replies``: how many of a post's replies it publishes with the post, by
    platform (as a first comment, or a thread's tail); the rest are the
    author's to post by hand. ``metrics``: the platforms it reports numbers
    for; anywhere else they are typed in from the platform's own analytics.
    ``strips_links``: the platforms where it silently deletes every link from
    the post itself, which makes a link there a copy problem."""

    id: str
    label: str
    key: VendorKey
    dashboard_url: str
    replies: Mapping[str, int] = field(default_factory=dict)
    metrics: frozenset[str] = frozenset()
    strips_links: frozenset[str] = frozenset()
    # Set where the vendor says something about a platform's numbers that a
    # person has to act on (Zernio bills X's reads, so they are opt-in there).
    metrics_notes: Mapping[str, str] = field(default_factory=dict)

    def replies_for(self, platform: str) -> int:
        return self.replies.get(platform, 0)

    def reports_metrics(self, platform: str) -> bool:
        return platform in self.metrics

    def strips_links_on(self, platform: str) -> bool:
        return platform in self.strips_links


class Publisher(Protocol):
    """One scheduler, opened on one person's key. Used as ``async with``."""

    spec: PublisherSpec

    async def __aenter__(self) -> Publisher: ...
    async def __aexit__(self, *exc: Any) -> None: ...

    async def list_accounts(self, platform: str | None = None) -> list[SocialAccount]: ...

    async def upload(self, data: bytes, *, name: str, mime_type: str) -> MediaRef: ...

    async def create_post(self, post: Outgoing) -> RemotePost:
        """A refusal raises; a post the scheduler accepted and then failed
        comes back with ``status`` FAILED."""
        ...

    async def get_post(self, post_id: str) -> RemotePost:
        """Raises ``PublisherError`` with ``not_found`` when the scheduler no
        longer holds it."""
        ...

    async def update_words(self, remote: RemotePost, caption: str, replies: tuple[str, ...]) -> None:
        """New words for a post still scheduled (``remote`` is what
        ``get_post`` just returned), keeping its time."""
        ...

    async def delete_post(self, post_id: str) -> None:
        """Take a post off the queue. Gone already is fine; raises
        ``PostAlreadyOut`` for a post the scheduler already published."""
        ...

    async def fetch_metrics(self, post_id: str, *, platform: str, ref: str = "") -> PostMetrics | None:
        """The post's numbers, with its daily history where the scheduler
        keeps one; None while they have not synced yet."""
        ...

    async def reported_posts(self, *, refresh: bool = False) -> list[ReportedPost]:
        """Every post the scheduler reports numbers for, newest first."""
        ...
