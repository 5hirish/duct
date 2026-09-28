"""What a post becomes at PostBridge, and what PostBridge's answer does to it.

Two callers publish: the agent's ``publish_post`` tool and the app's publish
route. Each used to build the request and record the result its own way, and
they drifted — the route stamped ``scheduled_at`` and ``published_via``, the
tool did not (#272), so a post the agent scheduled never appeared on its date
in the calendar. Both now take the words, the platform options and the
bookkeeping from here. The media each uploads is still its own choice: the
tool prefers composed slide renders, the route uploads what the post links.

Pure: no DB, no network. The callers own the session and the client.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agents.content.channels import RULES, copy_problems, primary_channel, resolve
from agents.content.schema import ContentStatus, TEXT_POST_TYPE
from service.post_bridge.schema import (
    PostBridgeCreatePostRequest,
    PostBridgePost,
    PostBridgePostStatus,
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


def create_request(
    post,
    *,
    social_account_ids: list[int],
    media_ids: list[str],
    scheduled_at: datetime | None,
    tiktok_draft: bool = False,
) -> PostBridgeCreatePostRequest:
    """The PostBridge request for a post: its words, its media (none for a
    text post), and the first reply as a ``first_comment`` on every platform
    that posts one. Set per platform, so a cross-post to TikTok carries none."""
    configs: dict[str, dict] = {}
    if tiktok_draft:
        configs["tiktok"] = {"draft": True}
    replies = [r for r in (post.replies or []) if isinstance(r, str) and r.strip()]
    if replies:
        for platform in _REPLY_PLATFORMS:
            configs[platform] = {"first_comment": replies[0]}
    return PostBridgeCreatePostRequest(
        caption=post.caption or "",
        social_accounts=social_account_ids,
        media=media_ids or None,
        scheduled_at=scheduled_at,
        platform_configurations=configs or None,
    )


def record_published(post, resp: PostBridgePost, scheduled_at: datetime | None) -> None:
    """Write PostBridge's answer onto the row: its id, where the post came
    from, when it is due, and the status the board and calendar read."""
    post.post_bridge_post_id = resp.id
    post.published_via = PUBLISHED_VIA_DUCT
    if scheduled_at is not None:
        post.scheduled_at = scheduled_at
    if resp.status == PostBridgePostStatus.POSTED:
        post.status = ContentStatus.POSTED.value
        post.posted_at = datetime.now(timezone.utc)
    elif resp.status == PostBridgePostStatus.SCHEDULED:
        post.status = ContentStatus.SCHEDULED.value
    else:
        post.status = resp.status.value


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
    "create_request",
    "is_text_only",
    "metrics_sync",
    "no_sync_message",
    "publish_blockers",
    "record_published",
    "unpublished_replies",
]
