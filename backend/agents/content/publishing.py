"""What a post becomes at its scheduler, and what the scheduler's answer does to it.

Two callers publish: the agent's ``publish_post`` tool and the app's publish
route. Each used to build the request, choose the media and record the result
its own way, and they drifted twice. The route stamped ``scheduled_at`` and
``published_via`` and the tool did not (#272), so a post the agent scheduled
never appeared on its date in the calendar. Then the route read only
``/uploads/`` paths off local disk, so on hosted Duct, whose pictures live on
R2, the Publish button found nothing to send; and where it did find files it
sent every raw image beside the composed slides. Both now take the words, the
media, the platform options and the bookkeeping from here. Only a refusal's
wording stays with each caller, because one is read by a person and the
other by the model.

Which scheduler a post goes through is the connector its account is linked
at (``ContentSocialLink.publisher``), and once it is sent the post records
it (``ContentPost.publisher``): the scheduler holding a queued post is the
only one that can change or cancel it. Everything here speaks the port
(``service/publishers``), never a vendor.

A post scheduled through Duct lives in two places until it goes out, and
three writers can change it here: the edit route, the delete route and the
agent's rewrite. ``push_edit`` and ``cancel`` are how each of them keeps the
scheduler's copy the same, so the queue never publishes words the person
already changed or a post they already deleted. ``settle`` closes the loop
once the time has passed: it asks the scheduler what became of the post, and
``pull_metrics`` reads its numbers afterwards, for the sync route, the daily
refresh and the agent's ``log_metrics`` alike.

Nothing here opens a connection of its own: rows come through the session a
caller passes, the scheduler through the publisher it opens, and media bytes
through ``service.storage``, which serves R2 and local disk alike.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import UUID

from sqlmodel import Session, select

from agents.content.channels import copy_problems, primary_channel, resolve
from agents.content.schema import ContentStatus, TEXT_POST_TYPE
from agents.content.video import VIDEO_POST_TYPE, publish_asset
from models.content import ContentAsset, ContentSocialLink
from service import storage
from service.content_metrics import merge_synced_metrics
from service.publishers import (
    Outgoing,
    PostAlreadyOut,
    PostMetrics,
    Publisher,
    PublisherError,
    PublisherSpec,
    RemotePost,
    RemoteStatus,
    Target,
)
from service.publishers.registry import NO_SCHEDULER, connected_specs, spec_for
from utils.dates import utcnow

# ContentPost.published_via for a post that went out through Duct.
PUBLISHED_VIA_DUCT = "duct"


def is_text_only(post) -> bool:
    """A text post with no picture: it publishes with no media at all."""
    return post.post_type == TEXT_POST_TYPE and not [s for s in (post.slides or []) if isinstance(s, dict)]


def _replies(post) -> tuple[str, ...]:
    return tuple(r for r in (post.replies or []) if isinstance(r, str) and r.strip())


def unpublished_replies(post, spec: PublisherSpec | None) -> int:
    """How many of the post's replies its scheduler does not publish — the
    ones the author posts by hand. Not a reason to refuse: a post with a reply
    the channel cannot carry still goes out, alone, and the reply is theirs to
    paste."""
    ch = resolve(primary_channel(post.platforms))
    return max(0, len(_replies(post)) - (spec.replies_for(ch.id) if spec else 0))


def publish_blockers(post, spec: PublisherSpec | None = None) -> list[str]:
    """Why this post cannot go out as it stands — sentences for the person or
    the model — or an empty list. Only what the platform, or the scheduler
    ``spec`` it would go through, would refuse: the review's softer advice
    never blocks, and neither do replies the channel does not publish
    (``unpublished_replies``)."""
    ch = resolve(primary_channel(post.platforms))
    caption = post.caption or ""
    replies = [r for r in (post.replies or []) if isinstance(r, str)]
    problems: list[str] = []
    # A post a scheduler already holds is not published again. A second
    # create uploaded the media again, made a second post, and overwrote the
    # id on the row, so every later edit, unschedule and delete reached the
    # second post and the first went out untouched. Both publish paths share
    # this list, which is why the check lives here and not in either caller.
    if post.publisher_post_id and post.status == ContentStatus.SCHEDULED:
        problems.append(
            f"This post is already scheduled through Duct for {post.scheduled_at:%d %b %H:%M}"
            if post.scheduled_at else "This post is already scheduled through Duct"
        )
        problems[-1] += "; edit it in place or unschedule it first."
    elif post.status == ContentStatus.POSTED:
        problems.append("This post already went out; publishing it again would post it twice.")
    if not caption.strip():
        problems.append("The post has no words yet.")
    problems += copy_problems(ch.id, caption, replies, strips_links=bool(spec and spec.strips_links_on(ch.id)))
    if is_text_only(post) and ch.rules.requires_media:
        problems.append(f"{ch.label} doesn't take a post without a picture or video.")
    return problems


def due_at(value: datetime | None) -> datetime | None:
    """A schedule time as the instant it names, in UTC.

    The picker's time once reached the server with no zone and was read as
    UTC, so a post set for 9:00 in Madrid went out at 11:00. The app now
    sends the offset; a time that still arrives without one is read as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def publish_failure(remote: RemotePost, spec: PublisherSpec) -> str | None:
    """Why the scheduler refused a post it accepted the request for, or None.
    A failed post is not published and must not be recorded as if it were."""
    if remote.status != RemoteStatus.FAILED:
        return None
    return f"{spec.label} couldn't publish the post. {remote.failure_reason or 'It gave no reason.'}"


def record_published(post, remote: RemotePost, scheduled_at: datetime | None, spec: PublisherSpec) -> None:
    """Write the scheduler's answer onto the row: which scheduler holds it and
    its id there, where the post came from, when it is due, and the status
    the board and calendar read.

    A post going out right now is posted: the board has no column for a
    scheduler's own word, and a post filed under one vanished from it.
    Callers check ``publish_failure`` first."""
    if remote.status == RemoteStatus.FAILED:
        raise ValueError("A failed post is not published; check publish_failure first.")
    post.publisher = spec.id
    post.publisher_post_id = remote.id
    post.publisher_metrics_id = ""
    post.published_via = PUBLISHED_VIA_DUCT
    if scheduled_at is not None:
        post.scheduled_at = due_at(scheduled_at)
    if remote.status == RemoteStatus.SCHEDULED:
        post.status = ContentStatus.SCHEDULED.value
    else:
        post.status = ContentStatus.POSTED.value
        post.posted_at = utcnow()
        post.published_url = post.published_url or remote.url


# ---------------------------------------------------------------------------
# What a post sends, and which account sends it
# ---------------------------------------------------------------------------

# ContentAsset.asset_type of a slide rasterized with its caption and layout
# baked in (agents/content/tools._persist_slide_render).
SLIDE_RENDER = "slide_render"


@dataclass(frozen=True)
class MediaFile:
    """One file a post publishes: where storage holds it and what the scheduler
    calls it. Plain data, so it can be read on a worker thread."""

    url: str
    name: str
    mime_type: str


@dataclass
class MediaPick:
    """What a post publishes, in the order it appears on the post.
    ``missing`` names slides with nothing composed to send; ``uncomposed``
    names slides going out as their raw photo, without their captions."""

    files: list[MediaFile] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    uncomposed: list[str] = field(default_factory=list)


class MediaUnreadable(Exception):
    """A file the post publishes could not be read back from storage."""

    def __init__(self, file: MediaFile) -> None:
        super().__init__(f"couldn't read {file.url}")
        self.file = file


def _media_file(asset: ContentAsset, position: int) -> MediaFile:
    return MediaFile(
        url=asset.url,
        name=asset.filename or PurePosixPath(asset.url).name or f"media-{position}",
        mime_type=asset.mime_type or "image/png",
    )


def pick_media(db: Session, post, *, allow_uncomposed: bool) -> MediaPick:
    """The files a post publishes.

    A video post sends its cut alone, not the keyframes and references that
    also carry its id. A slideshow sends each slide's composed render (the
    latest, when it was rendered twice), which is the slide as it will look;
    never the raw photo underneath as well. A slide with no render goes as
    its raw photo only when the caller allows it and the slide has a single
    picture: a collage or a before-and-after means nothing uncomposed. A
    text post sends nothing; a post with no structured slides (older rows)
    sends whatever is linked to it."""
    if post.post_type == VIDEO_POST_TYPE:
        clip = publish_asset(db, post)
        return MediaPick(files=[_media_file(clip, 1)] if clip else [])
    if is_text_only(post):
        return MediaPick()
    assets = db.exec(
        select(ContentAsset)
        .where(ContentAsset.post_id == post.id, ContentAsset.project_id == post.project_id)
        .order_by(ContentAsset.created_at)
    ).all()
    slides = [s for s in (post.slides or []) if isinstance(s, dict)]
    if not slides:
        return MediaPick(files=[_media_file(a, i) for i, a in enumerate(assets, 1)])

    renders: dict[str, ContentAsset] = {}
    by_url: dict[str, ContentAsset] = {}
    for a in assets:
        slide_id = (a.params or {}).get("slide_id")
        if a.asset_type == SLIDE_RENDER and slide_id:
            renders[str(slide_id)] = a   # oldest first, so the latest render wins
        if a.url:
            by_url.setdefault(a.url, a)

    pick = MediaPick()
    for s in slides:
        sid = str(s.get("slide_id") or "")
        chosen = renders.get(sid)
        if chosen is None:
            photo = by_url.get(s.get("image_url") or "")
            if allow_uncomposed and photo is not None and not s.get("items"):
                chosen = photo
                pick.uncomposed.append(sid or "(unnamed)")
            else:
                pick.missing.append(sid or "(unnamed)")
                continue
        pick.files.append(_media_file(chosen, len(pick.files) + 1))
    return pick


async def load_media(files: list[MediaFile]) -> list[tuple[bytes, MediaFile]]:
    """Every file's bytes, read before anything is uploaded so a missing one
    costs no half-sent post. Off the event loop, because on R2 each read is an
    HTTP request and a slideshow is several. Raises ``MediaUnreadable``."""

    def read_all() -> list[tuple[bytes, MediaFile]]:
        out: list[tuple[bytes, MediaFile]] = []
        for f in files:
            data = storage.get_bytes(f.url)
            if not data:
                raise MediaUnreadable(f)
            out.append((data, f))
        return out

    return await asyncio.to_thread(read_all)


async def send_post(
    pub: Publisher,
    post,
    media: list[tuple[bytes, MediaFile]],
    *,
    targets: list[Target],
    scheduled_at: datetime | None,
    tiktok_draft: bool = False,
) -> RemotePost:
    """Upload ``media`` in order, then create the post with its words and
    every reply; the scheduler publishes as many of those as it can. A refusal
    raises ``PublisherError``; a post the scheduler accepted and then failed
    comes back for ``publish_failure`` to read."""
    refs = [await pub.upload(data, name=f.name, mime_type=f.mime_type) for data, f in media]
    return await pub.create_post(Outgoing(
        caption=post.caption or "",
        targets=tuple(targets),
        replies=_replies(post),
        media=tuple(refs),
        scheduled_at=due_at(scheduled_at),
        tiktok_draft=tiktok_draft,
    ))


# ---------------------------------------------------------------------------
# Which scheduler, and which account
# ---------------------------------------------------------------------------


def linked_accounts(db: Session, project_id: UUID) -> list[ContentSocialLink]:
    return list(db.exec(
        select(ContentSocialLink)
        .where(ContentSocialLink.project_id == project_id)
        .order_by(ContentSocialLink.created_at)
    ).all())


@dataclass
class ProjectPublishing:
    """Which scheduler serves each of a project's channels, worked out once
    for a listing: the one holding the account the project linked for that
    channel, else the owner's only connected scheduler, else none. Nothing is
    a default: with two connected and nothing linked, a channel has none."""

    by_channel: dict[str, PublisherSpec] = field(default_factory=dict)
    only: PublisherSpec | None = None
    connected: list[PublisherSpec] = field(default_factory=list)

    def for_channel(self, channel: str | None) -> PublisherSpec | None:
        return self.by_channel.get(resolve(channel).id) or self.only

    def for_post(self, post) -> PublisherSpec | None:
        """The scheduler holding the post once it was sent, else its channel's."""
        return spec_for(post.publisher) or self.for_channel(primary_channel(post.platforms))


def project_publishing(db: Session, project_id: UUID, owner_id: UUID) -> ProjectPublishing:
    connected = connected_specs(owner_id, db)
    by_channel: dict[str, PublisherSpec] = {}
    for link in linked_accounts(db, project_id):
        spec = spec_for(link.publisher)
        if spec is not None and spec.id in {s.id for s in connected}:
            by_channel.setdefault(resolve(link.platform).id, spec)
    return ProjectPublishing(by_channel, connected[0] if len(connected) == 1 else None, connected)


def default_account(db: Session, post) -> tuple[ContentSocialLink | None, str]:
    """The account a post goes to when its publisher names none, as
    ``(link, "")``, or ``(None, why)`` naming what there is.

    The one account this project linked for the post's platform (Content →
    Accounts). None, or several, is a sentence rather than a guess, and never
    a fall back to the other accounts on the owner's scheduler: one key can
    hold several brands' accounts, and the project's links are what say which
    of them are this project's."""
    channel = resolve(primary_channel(post.platforms))
    linked = linked_accounts(db, post.project_id)
    here = [r for r in linked if resolve(r.platform).id == channel.id]

    def named(rows: list[ContentSocialLink]) -> str:
        return ", ".join(
            f"@{r.username or '?'} ({resolve(r.platform).label}, id {r.external_account_id})" for r in rows
        )

    if len(here) == 1:
        return here[0], ""
    if here:
        return None, (
            f"This project links {len(here)} {channel.label} accounts: {named(here)}. "
            "Ask which one to post from and pass its id in social_account_ids."
        )
    if linked:
        return None, (
            f"No {channel.label} account is linked to this project (it links {named(linked)}). "
            f"Ask the user to link their {channel.label} account in Content → Accounts."
        )
    return None, (
        "This project has no linked social accounts. Ask the user to connect a scheduler and link the "
        f"{channel.label} account to post from in Content → Accounts."
    )


def chosen_publisher(db: Session, project_id: UUID, account_ids: list[str], publishing: ProjectPublishing) -> tuple[PublisherSpec | None, str]:
    """The scheduler holding every account in ``account_ids``, as
    ``(spec, "")``, or ``(None, why)``. A post goes through one scheduler, so
    accounts linked at two are a choice the person makes, not a split."""
    if not publishing.connected:
        return None, NO_SCHEDULER
    held = {link.external_account_id: link.publisher for link in linked_accounts(db, project_id)}
    ids = {held[a] for a in account_ids if held.get(a)}
    if len(ids) > 1:
        return None, "Those accounts are at different schedulers; publish to one scheduler's accounts at a time."
    if ids and (spec := spec_for(ids.pop())) is not None:
        if spec.id not in {s.id for s in publishing.connected}:
            return None, f"{spec.label} isn't connected any more. Connect it again in Content → Accounts."
        return spec, ""
    if publishing.only is not None:
        return publishing.only, ""
    return None, "Those accounts aren't linked to this project. Link them in Content → Accounts first."


# ---------------------------------------------------------------------------
# A scheduled post, kept in step with its scheduler's queue
# ---------------------------------------------------------------------------


def is_queued_at_publisher(post) -> bool:
    return bool(post.publisher_post_id) and post.status == ContentStatus.SCHEDULED


def words_changed(post, before_caption: str | None, before_replies: list | None) -> bool:
    """Whether the row's words moved away from what the scheduler was given:
    the caption and the replies. Pictures are not compared; they were
    uploaded when the post was scheduled and an edit does not re-send them."""
    before = tuple(r for r in (before_replies or []) if isinstance(r, str) and r.strip())
    return (post.caption or "") != (before_caption or "") or _replies(post) != before


def forget_schedule(post) -> None:
    """The scheduler no longer holds the post: it is a draft again."""
    post.publisher = ""
    post.publisher_post_id = ""
    post.publisher_metrics_id = ""
    post.published_via = ""
    post.scheduled_at = None
    post.status = ContentStatus.DRAFT.value


def went_out(post) -> None:
    post.status = ContentStatus.POSTED.value
    post.posted_at = post.posted_at or utcnow()


async def _held(pub: Publisher, post) -> RemotePost | None:
    """The scheduler's copy of the post, or None (and the row a draft again)
    when it no longer holds one."""
    try:
        return await pub.get_post(post.publisher_post_id)
    except PublisherError as exc:
        if exc.not_found:
            forget_schedule(post)
            return None
        raise


async def push_edit(pub: Publisher, post) -> None:
    """Carry a queued post's new words to its scheduler.

    A post the scheduler no longer holds, or whose slot failed, is a draft
    again; one it already sent raises ``PostAlreadyOut``. The time is read
    back from the scheduler and kept, because an update without one publishes
    at once on PostBridge, and posts the agent scheduled before #272 never
    stored one."""
    remote = await _held(pub, post)
    if remote is None:
        return
    if remote.status in (RemoteStatus.FAILED, RemoteStatus.CANCELLED):
        forget_schedule(post)
        return
    if remote.status != RemoteStatus.SCHEDULED or remote.scheduled_at is None:
        raise PostAlreadyOut()
    await pub.update_words(remote, post.caption or "", _replies(post))


async def cancel(pub: Publisher, post) -> None:
    """Take a queued post off its scheduler's queue; the row becomes a draft.
    Gone already is fine; a post the scheduler published raises
    ``PostAlreadyOut``."""
    await pub.delete_post(post.publisher_post_id)
    forget_schedule(post)


async def settle(pub: Publisher, post) -> str | None:
    """Ask the scheduler what became of a scheduled post whose time has
    passed, and write the answer on the row (#311: nothing else ever asked, so
    a post showed Scheduled for ever after it went out). Returns the
    scheduler's reason when the post failed ("" when it gave none), else None.

    Out, or going out as we ask, is posted, on the rule ``record_published``
    follows; it keeps its link when the scheduler has one, and its time is
    when it was due, not whenever someone next opened the board. Failed is
    failed. Still queued is left alone, except that a post the agent
    scheduled before #272 learns its time here. A post the scheduler no
    longer holds, or took back, is a draft again.

    Raises ``PublisherError`` before writing anything, so a caller that
    swallows it leaves the row as it was."""
    remote = await _held(pub, post)
    if remote is None:
        return None
    if remote.status == RemoteStatus.SCHEDULED:
        if post.scheduled_at is None:
            post.scheduled_at = due_at(remote.scheduled_at)
        return None
    if remote.status == RemoteStatus.FAILED:
        post.status = ContentStatus.FAILED.value
        return remote.failure_reason
    if remote.status in (RemoteStatus.CANCELLED, RemoteStatus.DRAFT):
        forget_schedule(post)
        return None
    post.posted_at = post.posted_at or due_at(remote.scheduled_at) or post.scheduled_at
    went_out(post)
    post.published_url = post.published_url or remote.url
    return None


# ---------------------------------------------------------------------------
# Its numbers
# ---------------------------------------------------------------------------


def metrics_sync(post, spec: PublisherSpec | None) -> bool:
    """Whether the post's scheduler reports this post's numbers. Where it
    does not, they are typed in from the platform's own analytics, and a
    sync would return nothing."""
    return bool(spec) and spec.reports_metrics(resolve(primary_channel(post.platforms)).id)


def no_sync_message(post, spec: PublisherSpec | None) -> str:
    label = resolve(primary_channel(post.platforms)).label
    if spec is None:
        return f"{label} numbers sync from the scheduler a post went out through. Type them into the post's metrics."
    return (
        f"{spec.label} doesn't report {label} numbers. Read them off {label}'s own "
        "analytics and type them into the post's metrics."
    )


def not_synced_yet(post, spec: PublisherSpec) -> str:
    channel = resolve(primary_channel(post.platforms))
    note = spec.metrics_notes.get(channel.id, "")
    return " ".join(filter(None, (
        f"{spec.label} hasn't reported numbers for this post yet. Try again in a few minutes.", note,
    )))


async def pull_metrics(pub: Publisher, post) -> PostMetrics | None:
    """Read the post's numbers from its scheduler into ``perf`` and
    ``daily_perf``, and keep the handle they were read by. None while they
    have not synced yet; the row is left as it was. Numbers the person typed
    in stay theirs (``merge_synced_metrics``)."""
    got = await pub.fetch_metrics(
        post.publisher_post_id,
        platform=resolve(primary_channel(post.platforms)).id,
        ref=post.publisher_metrics_id,
    )
    if got is None:
        return None
    post.perf = merge_synced_metrics(post.perf, dict(got.values), synced_at=got.synced_at)
    post.publisher_metrics_id = got.ref
    if got.daily:
        post.daily_perf = [dict(d) for d in got.daily]
    return got


__all__ = [
    "PUBLISHED_VIA_DUCT",
    "SLIDE_RENDER",
    "MediaFile",
    "MediaPick",
    "MediaUnreadable",
    "PostAlreadyOut",
    "ProjectPublishing",
    "cancel",
    "chosen_publisher",
    "default_account",
    "due_at",
    "forget_schedule",
    "is_queued_at_publisher",
    "is_text_only",
    "linked_accounts",
    "load_media",
    "metrics_sync",
    "no_sync_message",
    "not_synced_yet",
    "pick_media",
    "project_publishing",
    "publish_blockers",
    "publish_failure",
    "pull_metrics",
    "push_edit",
    "record_published",
    "send_post",
    "settle",
    "unpublished_replies",
    "went_out",
    "words_changed",
]
