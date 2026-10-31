"""What a post becomes at PostBridge, and what PostBridge's answer does to it.

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

A post scheduled through PostBridge lives in two places until it goes out,
and three writers can change it here: the edit route, the delete route and
the agent's rewrite. ``push_edit`` and ``cancel`` are how each of them keeps
PostBridge's copy the same, so the queue never publishes words the person
already changed or a post they already deleted. ``settle`` closes the loop
once the time has passed: it asks PostBridge what became of the post.

Nothing here opens a connection of its own: rows come through the session a
caller passes, PostBridge through the client it opens, and media bytes
through ``service.storage``, which serves R2 and local disk alike.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from sqlmodel import Session, select

from agents.content.channels import RULES, copy_problems, primary_channel, resolve
from agents.content.schema import ContentStatus, TEXT_POST_TYPE
from agents.content.video import VIDEO_POST_TYPE, publish_asset
from models.content import ContentAsset, ContentSocialLink
from service import storage
from service.post_bridge.client import PostBridgeAPIError
from service.post_bridge.schema import (
    PostBridgeCreatePostRequest,
    PostBridgePost,
    PostBridgePostResult,
    PostBridgePostStatus,
    PostBridgeUpdatePostRequest,
)
from utils.dates import utcnow

# ContentPost.published_via for a post that went out through Duct.
PUBLISHED_VIA_DUCT = "duct"

# The platforms that post a reply with the post, as PostBridge's first_comment.
# Read off the rules table so a platform gains it in one place.
_REPLY_PLATFORMS: tuple[str, ...] = tuple(
    str(p) for p, rules in RULES.items() if rules.publishable_replies > 0
)

# PostBridge's analytics sync takes only these as a platform filter; Facebook
# is reported but not filterable, so it syncs unfiltered.
_SYNC_FILTERS = frozenset({"tiktok", "youtube", "instagram"})


def is_text_only(post) -> bool:
    """A text post with no picture: it publishes with no media at all."""
    return post.post_type == TEXT_POST_TYPE and not [s for s in (post.slides or []) if isinstance(s, dict)]


def unpublished_replies(post) -> int:
    """How many of the post's replies the channel does not publish — the ones
    the author posts by hand. Not a reason to refuse: a LinkedIn post with a
    first comment still goes out, alone, and the comment is theirs to paste."""
    ch = resolve(primary_channel(post.platforms))
    replies = [r for r in (post.replies or []) if isinstance(r, str) and r.strip()]
    return max(0, len(replies) - ch.rules.publishable_replies)


def publish_blockers(post) -> list[str]:
    """Why this post cannot go out as it stands — sentences for the person or
    the model — or an empty list. Only what the platform itself would refuse:
    the review's softer advice never blocks, and neither do replies the
    channel does not publish (``unpublished_replies``)."""
    ch = resolve(primary_channel(post.platforms))
    caption = post.caption or ""
    replies = [r for r in (post.replies or []) if isinstance(r, str)]
    problems: list[str] = []
    # A post PostBridge already holds is not published again. A second create
    # uploaded the media again, made a second post, and overwrote the id on
    # the row, so every later edit, unschedule and delete reached the second
    # post and the first went out untouched. Both publish paths share this
    # list, which is why the check lives here and not in either caller.
    if post.post_bridge_post_id and post.status == ContentStatus.SCHEDULED:
        problems.append(
            f"This post is already scheduled through Duct for {post.scheduled_at:%d %b %H:%M}"
            if post.scheduled_at else "This post is already scheduled through Duct"
        )
        problems[-1] += "; edit it in place or unschedule it first."
    elif post.status == ContentStatus.POSTED:
        problems.append("This post already went out; publishing it again would post it twice.")
    if not caption.strip():
        problems.append("The post has no words yet.")
    problems += copy_problems(ch.id, caption, replies)
    if is_text_only(post) and ch.rules.requires_media:
        problems.append(f"{ch.label} doesn't take a post without a picture or video.")
    return problems


def _first_reply(replies: list | None) -> str:
    return next((r for r in (replies or []) if isinstance(r, str) and r.strip()), "")


def _reply_configs(post) -> dict[str, dict]:
    """The first reply as a ``first_comment`` on every platform that posts
    one. Set per platform, so a cross-post to TikTok carries none."""
    first = _first_reply(post.replies)
    if not first:
        return {}
    return {platform: {"first_comment": first} for platform in _REPLY_PLATFORMS}


def due_at(value: datetime | None) -> datetime | None:
    """A schedule time as the instant it names, in UTC.

    The picker's time once reached the server with no zone and was read as
    UTC, so a post set for 9:00 in Madrid went out at 11:00. The app now
    sends the offset; a time that still arrives without one is read as UTC,
    which is what PostBridge would have made of it anyway."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_request(
    post,
    *,
    social_account_ids: list[int],
    media_ids: list[str],
    scheduled_at: datetime | None,
    tiktok_draft: bool = False,
) -> PostBridgeCreatePostRequest:
    """The PostBridge request for a post: its words, its media (none for a
    text post), and its first reply where the platform posts one."""
    configs: dict[str, dict] = {}
    if tiktok_draft:
        configs["tiktok"] = {"draft": True}
    configs.update(_reply_configs(post))
    return PostBridgeCreatePostRequest(
        caption=post.caption or "",
        social_accounts=social_account_ids,
        media=media_ids or None,
        scheduled_at=due_at(scheduled_at),
        platform_configurations=configs or None,
    )


def _error_text(error: Any) -> str:
    """A post result's ``error``, which PostBridge sends as a string or as an
    object carrying one."""
    if isinstance(error, str):
        return error.strip()
    if isinstance(error, dict):
        return str(error.get("message") or error.get("error") or "").strip()
    return ""


def failure_reason(remote: PostBridgePost, results: Iterable[PostBridgePostResult] = ()) -> str:
    """PostBridge's own words for why a post did not go out, or "" when it
    gave none: the post's warnings, else what each account's attempt said.
    A post failed at create time carries warnings; one that failed at its
    scheduled time may only say so in its results."""
    words = [w for w in remote.warnings if w] or [_error_text(r.error) for r in results if not r.success]
    return " ".join(dict.fromkeys(w for w in words if w))


def publish_failure(resp: PostBridgePost) -> str | None:
    """Why PostBridge refused a post it accepted the request for, or None.
    A failed post is not published and must not be recorded as if it were."""
    if resp.status != PostBridgePostStatus.FAILED:
        return None
    why = failure_reason(resp) or "It gave no reason."
    return f"PostBridge couldn't publish the post. {why}"


def record_published(post, resp: PostBridgePost, scheduled_at: datetime | None) -> None:
    """Write PostBridge's answer onto the row: its id, where the post came
    from, when it is due, and the status the board and calendar read.

    ``processing`` is a post going out right now, so it is posted: the
    board has no column for PostBridge's own word, and a post filed under
    one vanished from it. Callers check ``publish_failure`` first."""
    if resp.status == PostBridgePostStatus.FAILED:
        raise ValueError("A failed post is not published; check publish_failure first.")
    post.post_bridge_post_id = resp.id
    post.published_via = PUBLISHED_VIA_DUCT
    if scheduled_at is not None:
        post.scheduled_at = due_at(scheduled_at)
    if resp.status == PostBridgePostStatus.SCHEDULED:
        post.status = ContentStatus.SCHEDULED.value
    else:
        post.status = ContentStatus.POSTED.value
        post.posted_at = utcnow()


# ---------------------------------------------------------------------------
# What a post sends, and which account sends it
# ---------------------------------------------------------------------------

# ContentAsset.asset_type of a slide rasterized with its caption and layout
# baked in (agents/content/tools._persist_slide_render).
SLIDE_RENDER = "slide_render"


@dataclass(frozen=True)
class MediaFile:
    """One file a post publishes: where storage holds it and what PostBridge
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
    pb,
    post,
    media: list[tuple[bytes, MediaFile]],
    *,
    social_account_ids: list[int],
    scheduled_at: datetime | None,
    tiktok_draft: bool = False,
) -> PostBridgePost:
    """Upload ``media`` in order, then create the post. A refusal raises
    ``PostBridgeAPIError``; a post PostBridge accepted and then failed comes
    back for ``publish_failure`` to read."""
    media_ids: list[str] = []
    for data, f in media:
        upload = await pb.create_upload_url(name=f.name, mime_type=f.mime_type, size_bytes=len(data))
        await pb.upload_media(data, upload.upload_url, f.mime_type)
        media_ids.append(upload.media_id)
    return await pb.create_post(create_request(
        post,
        social_account_ids=social_account_ids,
        media_ids=media_ids,
        scheduled_at=scheduled_at,
        tiktok_draft=tiktok_draft,
    ))


def default_account(db: Session, post) -> tuple[int | None, str]:
    """The account a post goes to when its publisher names none, as
    ``(id, "")``, or ``(None, why)`` naming what there is.

    The one account this project linked for the post's platform (Content →
    Accounts). None, or several, is a sentence rather than a guess, and never
    a fall back to the other accounts on the PostBridge key: one key can hold
    several brands' accounts, and the project's links are what say which of
    them are this project's."""
    channel = resolve(primary_channel(post.platforms))
    linked: list[tuple[int, ContentSocialLink]] = []
    for row in db.exec(
        select(ContentSocialLink)
        .where(ContentSocialLink.project_id == post.project_id)
        .order_by(ContentSocialLink.created_at)
    ).all():
        try:
            linked.append((int(row.external_account_id), row))
        except ValueError:
            continue
    here = [(i, r) for i, r in linked if resolve(r.platform).id == channel.id]

    def named(rows: list[tuple[int, ContentSocialLink]]) -> str:
        return ", ".join(f"@{r.username or '?'} ({resolve(r.platform).label}, id {i})" for i, r in rows)

    if len(here) == 1:
        return here[0][0], ""
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
        "This project has no linked social accounts. Ask the user to link the "
        f"{channel.label} account to post from in Content → Accounts."
    )


# ---------------------------------------------------------------------------
# A scheduled post, kept in step with PostBridge's queue
# ---------------------------------------------------------------------------


class PostAlreadyOut(Exception):
    """PostBridge has published the post, or is publishing it: nothing
    changed in Duct can reach it any more."""


def is_queued_at_postbridge(post) -> bool:
    return bool(post.post_bridge_post_id) and post.status == ContentStatus.SCHEDULED


def words_changed(post, before_caption: str | None, before_replies: list | None) -> bool:
    """Whether the row's words moved away from what PostBridge was given:
    the caption and the one reply it posts. Pictures are not compared; they
    were uploaded when the post was scheduled and an edit does not re-send
    them."""
    return (
        (post.caption or "") != (before_caption or "")
        or _first_reply(post.replies) != _first_reply(before_replies)
    )


def forget_schedule(post) -> None:
    """PostBridge no longer holds the post: it is a draft again."""
    post.post_bridge_post_id = ""
    post.published_via = ""
    post.scheduled_at = None
    post.status = ContentStatus.DRAFT.value


def went_out(post) -> None:
    post.status = ContentStatus.POSTED.value
    post.posted_at = post.posted_at or utcnow()


async def push_edit(pb, post) -> None:
    """Carry a queued post's new words to PostBridge.

    An update without ``scheduled_at`` publishes at once (PostBridge's own
    warning), so the time is read back from PostBridge and sent with every
    update rather than trusted from the row: posts the agent scheduled before
    #272 never stored one. A post PostBridge no longer holds, or whose slot
    failed, is a draft again; one it already sent raises ``PostAlreadyOut``.

    A reply deleted after scheduling stays at PostBridge: the API documents no
    way to clear a ``first_comment``, so an update without one leaves it."""
    try:
        remote = await pb.get_post(post.post_bridge_post_id)
    except PostBridgeAPIError as exc:
        if exc.status_code == 404:
            forget_schedule(post)
            return
        raise
    if remote.status == PostBridgePostStatus.FAILED:
        forget_schedule(post)
        return
    if remote.status != PostBridgePostStatus.SCHEDULED or remote.scheduled_at is None:
        raise PostAlreadyOut()
    reply_configs = _reply_configs(post)
    await pb.update_post(post.post_bridge_post_id, PostBridgeUpdatePostRequest(
        caption=post.caption or "",
        scheduled_at=remote.scheduled_at,
        platform_configurations=reply_configs or None,
    ))


async def cancel(pb, post) -> None:
    """Take a queued post off PostBridge's queue; the row becomes a draft.
    Gone already is fine. PostBridge refuses to delete a post it published,
    which raises ``PostAlreadyOut``."""
    try:
        await pb.delete_post(post.post_bridge_post_id)
    except PostBridgeAPIError as exc:
        if exc.status_code == 400:
            raise PostAlreadyOut() from exc
        if exc.status_code != 404:
            raise
    forget_schedule(post)


async def _post_results(pb, post_id: str) -> list[PostBridgePostResult]:
    """Best effort: the post's status alone settles it, and post-results is
    intermittently flaky on PostBridge's side (the analytics route
    self-heals result ids for the same reason)."""
    try:
        return await pb.list_post_results(post_id=post_id, limit=10)
    except PostBridgeAPIError:
        return []


async def settle(pb, post) -> str | None:
    """Ask PostBridge what became of a scheduled post whose time has passed,
    and write the answer on the row (#311: nothing else ever asked, so a post
    showed Scheduled for ever after it went out). Returns PostBridge's reason
    when the post failed ("" when it gave none), else None.

    Posted, or ``processing`` (going out as we ask), is posted, on the rule
    ``record_published`` follows; it keeps its link when a post result has
    one, and its time is when it was due, not whenever someone next opened
    the board. Failed is failed. Still queued is left alone, except that a
    post the agent scheduled before #272 learns its time here, so the
    calendar can place it and later loads leave it until it is due. A post
    PostBridge no longer holds is a draft again, as in ``push_edit``.

    Raises ``PostBridgeAPIError`` before writing anything, so a caller that
    swallows it leaves the row as it was."""
    try:
        remote = await pb.get_post(post.post_bridge_post_id)
    except PostBridgeAPIError as exc:
        if exc.status_code == 404:
            forget_schedule(post)
            return None
        raise
    if remote.status == PostBridgePostStatus.SCHEDULED:
        if post.scheduled_at is None:
            post.scheduled_at = due_at(remote.scheduled_at)
        return None
    results = await _post_results(pb, post.post_bridge_post_id)
    if remote.status == PostBridgePostStatus.FAILED:
        post.status = ContentStatus.FAILED.value
        return failure_reason(remote, results)
    post.posted_at = post.posted_at or due_at(remote.scheduled_at) or post.scheduled_at
    went_out(post)
    if not post.published_url:
        post.published_url = next(
            (r.platform_data.url for r in results if r.success and r.platform_data and r.platform_data.url),
            "",
        )
    return None


def metrics_sync(post) -> tuple[bool, str | None]:
    """Whether PostBridge reports this post's numbers, and the platform filter
    to sync with. X and LinkedIn are not reported: their numbers are typed in
    from the platform's own analytics, and a sync would return nothing."""
    channel = primary_channel(post.platforms)
    if not resolve(channel).rules.synced_metrics:
        return False, None
    return True, channel if channel in _SYNC_FILTERS else None


def no_sync_message(post) -> str:
    label = resolve(primary_channel(post.platforms)).label
    return (
        f"PostBridge doesn't report {label} numbers. Read them off {label}'s own "
        "analytics and type them into the post's metrics."
    )


__all__ = [
    "PUBLISHED_VIA_DUCT",
    "SLIDE_RENDER",
    "MediaFile",
    "MediaPick",
    "MediaUnreadable",
    "PostAlreadyOut",
    "cancel",
    "create_request",
    "default_account",
    "due_at",
    "failure_reason",
    "forget_schedule",
    "is_queued_at_postbridge",
    "is_text_only",
    "load_media",
    "metrics_sync",
    "no_sync_message",
    "pick_media",
    "publish_blockers",
    "publish_failure",
    "push_edit",
    "record_published",
    "send_post",
    "settle",
    "unpublished_replies",
    "went_out",
    "words_changed",
]
