"""Zernio as a ``Publisher`` (service/publishers/base.py).

Where Zernio differs from PostBridge, and why the spec says so:

- **Replies.** A post's replies go out as a thread on X and Threads
  (``threadItems``, the post itself first) and the first one as a first
  comment on LinkedIn, Instagram and Facebook, so far fewer are left for the
  author to paste.
- **Numbers.** Zernio reports LinkedIn and X as well. LinkedIn personal
  accounts report only posts published through Zernio, which every Duct post
  is. X's numbers cost X's read fee, so Zernio keeps them off until the
  person turns them on for the account.
- **Links.** Nothing is stripped from a post on X; a post with a link costs
  X's higher write fee instead, which Zernio passes through at cost.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from service.publishers.base import (
    Delivery,
    MediaRef,
    Outgoing,
    PostAlreadyOut,
    PostMetrics,
    PublisherError,
    PublisherSpec,
    RemotePost,
    RemoteStatus,
    ReportedPost,
    SocialAccount,
    Target,
)
from service.zernio.client import ZERNIO_KEY, ZernioAPIError, ZernioClient
from service.zernio.schema import ZernioAnalyticsPost, ZernioPost

logger = logging.getLogger(__name__)

# A thread longer than this is a blog post; Duct never drafts one.
MAX_THREAD_REPLIES = 24

_THREAD_PLATFORMS = frozenset({"twitter", "threads"})
_FIRST_COMMENT_PLATFORMS = frozenset({"linkedin", "instagram", "facebook"})

ZERNIO = PublisherSpec(
    id="zernio",
    label="Zernio",
    key=ZERNIO_KEY,
    dashboard_url="https://zernio.com/dashboard",
    replies={
        **{p: MAX_THREAD_REPLIES for p in _THREAD_PLATFORMS},
        **{p: 1 for p in _FIRST_COMMENT_PLATFORMS},
    },
    metrics=frozenset({
        "tiktok", "instagram", "youtube", "facebook", "linkedin", "twitter",
        "threads", "pinterest", "bluesky", "google_business",
    }),
    metrics_notes={
        "twitter": (
            "Zernio keeps X numbers off until you turn them on for the account in Zernio, "
            "because each read costs X's API fee."
        ),
    },
)

# Duct's channel ids that Zernio spells differently.
_TO_ZERNIO = {"google_business": "googlebusiness"}
_FROM_ZERNIO = {v: k for k, v in _TO_ZERNIO.items()}

_STATUS = {
    "draft": RemoteStatus.DRAFT,
    "pending_approval": RemoteStatus.DRAFT,
    "scheduled": RemoteStatus.SCHEDULED,
    "publishing": RemoteStatus.PUBLISHING,
    "published": RemoteStatus.PUBLISHED,
    "partial": RemoteStatus.PARTIAL,
    "failed": RemoteStatus.FAILED,
    "cancelled": RemoteStatus.CANCELLED,
}

# A platform entry's own status: pending, processing and uploading are on
# their way.
_DELIVERED = {"published": True, "failed": False, "cancelled": False}

_ANALYTICS_PAGE = 100
_ANALYTICS_PAGES = 10


def _platform(zernio_platform: str) -> str:
    return _FROM_ZERNIO.get(zernio_platform, zernio_platform)


@contextmanager
def _vendor() -> Iterator[None]:
    try:
        yield
    except ZernioAPIError as exc:
        raise PublisherError(
            _words(exc), status_code=exc.status_code, code=exc.error.code or exc.error.type,
        ) from exc


def _words(exc: ZernioAPIError) -> str:
    if exc.status_code == 402:
        return "Zernio's analytics need the Analytics add-on on your Zernio plan."
    return exc.error.error or str(exc)


def _remote(post: ZernioPost, warnings: list[str] = ()) -> RemotePost:
    return RemotePost(
        id=post.id,
        # A status Zernio adds later reads as on its way: never one that
        # would let Duct publish the post a second time.
        status=_STATUS.get(post.status, RemoteStatus.PUBLISHING),
        scheduled_at=post.scheduled_for,
        deliveries=tuple(
            Delivery(
                account_id=t.account_id,
                platform=_platform(t.platform),
                ok=_DELIVERED.get(t.status),
                url=t.platform_post_url or "",
                error=(t.error_message or "") if _DELIVERED.get(t.status) is False else "",
            )
            for t in post.platforms
        ),
        warnings=tuple(w for w in warnings if w),
    )


def _media_item(ref: MediaRef) -> dict:
    return {"url": ref.id, "type": "video" if ref.mime_type.startswith("video/") else "image"}


def _platform_data(platform: str, caption: str, replies: tuple[str, ...], media: list[dict], *, tiktok_draft: bool) -> dict:
    """What one platform entry carries beyond the shared words: its replies,
    the shape its platform takes them in, and TikTok's draft switch."""
    said = [r for r in replies if r.strip()]
    data: dict[str, Any] = {}
    if platform in _THREAD_PLATFORMS and said:
        # With threadItems the top-level content is not published, so the
        # post itself, and its media, go first.
        data["threadItems"] = [
            {"content": caption, **({"mediaItems": media} if media else {})},
            *({"content": r} for r in said[:MAX_THREAD_REPLIES]),
        ]
    elif platform in _FIRST_COMMENT_PLATFORMS and said:
        data["firstComment"] = said[0]
    if platform == "tiktok" and tiktok_draft:
        data["draft"] = True
    return data


class ZernioPublisher:
    spec = ZERNIO

    def __init__(self, api_key: str, *, client: ZernioClient | None = None) -> None:
        self._z = client or ZernioClient(api_key)
        self._platform_of: dict[str, str] | None = None
        # The media a fetched post carries, for an edit that rebuilds a
        # thread: its first item must keep the post's pictures.
        self._media_of: dict[str, list[dict]] = {}

    async def __aenter__(self) -> ZernioPublisher:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self._z.aclose()

    async def list_accounts(self, platform: str | None = None) -> list[SocialAccount]:
        with _vendor():
            accounts = await self._z.list_accounts(platform=_TO_ZERNIO.get(platform or "", platform))
        return [
            SocialAccount(
                id=a.id,
                platform=_platform(a.platform),
                username=a.username or a.display_name,
                display_name=a.display_name,
                avatar_url=a.profile_picture or "",
                needs_reconnect=a.needs_reconnection or not a.is_active,
            )
            for a in accounts
        ]

    async def _targets(self, targets: tuple[Target, ...]) -> list[Target]:
        """Every target with its platform, which Zernio needs and a caller
        holding only an account id does not know."""
        if all(t.platform for t in targets):
            return list(targets)
        if self._platform_of is None:
            self._platform_of = {a.id: a.platform for a in await self.list_accounts()}
        out: list[Target] = []
        for t in targets:
            platform = t.platform or self._platform_of.get(t.account_id, "")
            if not platform:
                raise PublisherError(f"Zernio has no connected account with id {t.account_id}.", status_code=404)
            out.append(Target(t.account_id, platform))
        return out

    async def upload(self, data: bytes, *, name: str, mime_type: str) -> MediaRef:
        with _vendor():
            presigned = await self._z.presign(filename=name, content_type=mime_type, size=len(data))
            await self._z.put_file(presigned.upload_url, data, mime_type)
        return MediaRef(id=presigned.public_url, mime_type=mime_type)

    async def create_post(self, post: Outgoing) -> RemotePost:
        media = [_media_item(m) for m in post.media]
        body: dict[str, Any] = {
            "content": post.caption,
            "platforms": [
                {
                    "platform": _TO_ZERNIO.get(t.platform, t.platform),
                    "accountId": t.account_id,
                    **({"platformSpecificData": data} if (data := _platform_data(
                        t.platform, post.caption, post.replies, media, tiktok_draft=post.tiktok_draft,
                    )) else {}),
                }
                for t in await self._targets(post.targets)
            ],
        }
        if media:
            body["mediaItems"] = media
        if post.scheduled_at is None:
            body["publishNow"] = True
        else:
            body["scheduledFor"] = post.scheduled_at.isoformat()
        with _vendor():
            answer = await self._z.create_post(body, idempotency_key=str(uuid.uuid4()))
        return _remote(answer.post, answer.warnings)

    async def get_post(self, post_id: str) -> RemotePost:
        with _vendor():
            post = await self._z.get_post(post_id)
        self._media_of[post.id] = post.media_items
        return _remote(post)

    async def update_words(self, remote: RemotePost, caption: str, replies: tuple[str, ...]) -> None:
        media = self._media_of.get(remote.id, [])
        body: dict[str, Any] = {
            "content": caption,
            "platforms": [
                {
                    "platform": _TO_ZERNIO.get(d.platform, d.platform),
                    "accountId": d.account_id,
                    **({"platformSpecificData": data} if (data := _platform_data(
                        d.platform, caption, replies, media, tiktok_draft=False,
                    )) else {}),
                }
                for d in remote.deliveries
            ],
        }
        if remote.scheduled_at is not None:
            body["scheduledFor"] = remote.scheduled_at.isoformat()
        with _vendor():
            await self._z.update_post(remote.id, body)

    async def delete_post(self, post_id: str) -> None:
        # Zernio deletes a post that is publishing, or partly out, whole,
        # analytics included, while what went out stays up: asked first, so
        # only a post still waiting is ever deleted.
        try:
            remote = await self.get_post(post_id)
        except PublisherError as exc:
            if exc.not_found:
                return
            raise
        if remote.status.is_out:
            raise PostAlreadyOut()
        try:
            await self._z.delete_post(post_id)
        except ZernioAPIError as exc:
            if exc.status_code == 404:
                return
            if exc.status_code == 400 and "published" in (exc.error.error or "").lower():
                raise PostAlreadyOut() from exc
            raise PublisherError(_words(exc), status_code=exc.status_code, code=exc.error.code) from exc

    async def fetch_metrics(self, post_id: str, *, platform: str, ref: str = "") -> PostMetrics | None:
        try:
            found = await self._z.post_analytics(post_id)
        except ZernioAPIError as exc:
            if exc.status_code == 424:
                raise PublisherError(
                    "Zernio couldn't publish this post on any platform, so it has no numbers.", status_code=424,
                ) from exc
            raise PublisherError(_words(exc), status_code=exc.status_code, code=exc.error.code) from exc
        if found is None:
            return None
        try:
            timeline = await self._z.post_timeline(post_id)
        except ZernioAPIError:
            logger.info("zernio: no timeline for %s yet", post_id)
            timeline = []
        zp = _TO_ZERNIO.get(platform, platform)
        return PostMetrics(
            ref=post_id,
            values=_perf(found),
            synced_at=found.analytics.last_updated,
            daily=tuple(
                # The shape PostBridge's daily snapshots have, which the app reads.
                {"snapshot_date": d.date, "view_count": d.views, "like_count": d.likes,
                 "comment_count": d.comments, "share_count": d.shares}
                for d in timeline
                if not d.platform or d.platform == zp
            ),
        )

    async def reported_posts(self, *, refresh: bool = False) -> list[ReportedPost]:
        # Zernio refreshes on its own (every 90 minutes for posts made
        # elsewhere, hourly for its own), so there is nothing to ask it to do.
        rows: list[ZernioAnalyticsPost] = []
        with _vendor():
            for page in range(1, _ANALYTICS_PAGES + 1):
                posts, pages = await self._z.list_analytics(page=page, limit=_ANALYTICS_PAGE)
                rows.extend(posts)
                if page >= pages:
                    break
        return [
            ReportedPost(
                ref=p.id,
                platform=_platform(p.platform),
                remote_post_id=p.late_post_id or "",
                title=p.content,
                url=p.platform_post_url or "",
                cover_url=p.thumbnail_url or "",
                views=p.analytics.views or p.analytics.impressions,
                likes=p.analytics.likes,
                comments=p.analytics.comments,
                shares=p.analytics.shares,
                posted_at=p.published_at,
                synced_at=p.analytics.last_updated,
            )
            for p in rows
        ]


def _perf(found: ZernioAnalyticsPost) -> dict[str, Any]:
    """Zernio's numbers as perf keys (service/content_metrics.METRIC_ALIASES).

    The four counts are always written, since every platform reports them.
    Everything else Zernio sends as 0 where the platform does not report it,
    and an unrecorded metric is unknown, never zero, so those are written
    only when they hold something."""
    a = found.analytics
    out: dict[str, Any] = {
        "views": a.views or a.impressions,
        "likes": a.likes,
        "comments": a.comments,
        "shares": a.shares,
    }
    for key, value in (("saves", a.saves), ("reach", a.reach), ("impressions", a.impressions), ("clicks", a.clicks)):
        if value:
            out[key] = value
    if a.ig_reels_avg_watch_time:
        out["avg_watch_time"] = round(a.ig_reels_avg_watch_time / 1000, 2)   # seconds
    if a.completion_rate:
        out["completion_rate"] = round(a.completion_rate * 100, 2)           # percent
    if found.platform_post_url:
        out["share_url"] = found.platform_post_url
    if found.thumbnail_url:
        out["cover_image_url"] = found.thumbnail_url
    return out
