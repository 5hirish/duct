"""What a post becomes at PostBridge, and what PostBridge's answer does to it.

Two callers publish: the agent's ``publish_post`` tool and the app's publish
route. Each used to build the request and record the result its own way, and
they drifted — the route stamped ``scheduled_at`` and ``published_via``, the
tool did not (#272), so a post the agent scheduled never appeared on its date
in the calendar. Both now take the words, the platform options and the
bookkeeping from here. The media each uploads is still its own choice: the
tool prefers composed slide renders, the route uploads what the post links.

A post scheduled through PostBridge lives in two places until it goes out,
and three writers can change it here: the edit route, the delete route and
the agent's rewrite. ``push_edit`` and ``cancel`` are how each of them keeps
PostBridge's copy the same, so the queue never publishes words the person
already changed or a post they already deleted.

No DB. The only network is through the client a caller opens and passes in.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agents.content.channels import RULES, copy_problems, primary_channel, resolve
from agents.content.schema import ContentStatus, TEXT_POST_TYPE
from service.post_bridge.client import PostBridgeAPIError
from service.post_bridge.schema import (
    PostBridgeCreatePostRequest,
    PostBridgePost,
    PostBridgePostStatus,
    PostBridgeUpdatePostRequest,
)

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
        scheduled_at=scheduled_at,
        platform_configurations=configs or None,
    )


def publish_failure(resp: PostBridgePost) -> str | None:
    """Why PostBridge refused a post it accepted the request for, or None.
    A failed post is not published and must not be recorded as if it were."""
    if resp.status != PostBridgePostStatus.FAILED:
        return None
    why = " ".join(w for w in resp.warnings if w) or "It gave no reason."
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
        post.scheduled_at = scheduled_at
    if resp.status == PostBridgePostStatus.SCHEDULED:
        post.status = ContentStatus.SCHEDULED.value
    else:
        post.status = ContentStatus.POSTED.value
        post.posted_at = datetime.now(timezone.utc)


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
    post.posted_at = post.posted_at or datetime.now(timezone.utc)


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
    "PostAlreadyOut",
    "cancel",
    "create_request",
    "forget_schedule",
    "is_queued_at_postbridge",
    "is_text_only",
    "metrics_sync",
    "no_sync_message",
    "publish_blockers",
    "publish_failure",
    "push_edit",
    "record_published",
    "unpublished_replies",
    "went_out",
    "words_changed",
]
