"""PostBridge as a ``Publisher`` (service/publishers/base.py).

PostBridge's own vocabulary stops here: numeric account ids, ``posted`` and
``processing``, a post's numbers reached through its post results, and a
first reply sent as ``first_comment``. Everything above this module reads
Duct's words for the same things.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from service.post_bridge.client import POSTBRIDGE_KEY, PostBridgeAPIError, PostBridgeClient
from service.post_bridge.schema import (
    PostBridgeCreatePostRequest,
    PostBridgePost,
    PostBridgePostResult,
    PostBridgePostStatus,
    PostBridgeUpdatePostRequest,
)
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
)

logger = logging.getLogger(__name__)

POSTBRIDGE = PublisherSpec(
    id="post_bridge",
    label="PostBridge",
    key=POSTBRIDGE_KEY,
    dashboard_url="https://app.post-bridge.com",
    # One reply, as a first_comment, on X and Threads; none elsewhere.
    replies={"twitter": 1, "threads": 1},
    metrics=frozenset({"tiktok", "youtube", "instagram", "facebook"}),
    # X charges more for a post with a link, so PostBridge deletes every link
    # from the post itself there, bare domains included, and says nothing.
    strips_links=frozenset({"twitter"}),
)

_STATUS = {
    PostBridgePostStatus.POSTED: RemoteStatus.PUBLISHED,
    PostBridgePostStatus.SCHEDULED: RemoteStatus.SCHEDULED,
    PostBridgePostStatus.PROCESSING: RemoteStatus.PUBLISHING,
    PostBridgePostStatus.FAILED: RemoteStatus.FAILED,
}

# PostBridge's analytics sync takes only these as a platform filter; Facebook
# is reported but not filterable, so it syncs unfiltered.
_SYNC_FILTERS = frozenset({"tiktok", "youtube", "instagram"})

# PostBridge caps an analytics page at 100; twenty pages is everything a
# project's Analytics tab has any use for.
_PAGE = 100
_MAX_PAGES = 20


@contextmanager
def _vendor() -> Iterator[None]:
    try:
        yield
    except PostBridgeAPIError as exc:
        raise PublisherError(
            exc.error.message or str(exc), status_code=exc.status_code, code=exc.error.code or "",
        ) from exc


def _error_text(error: Any) -> str:
    """A post result's ``error``, which PostBridge sends as a string or as an
    object carrying one."""
    if isinstance(error, str):
        return error.strip()
    if isinstance(error, dict):
        return str(error.get("message") or error.get("error") or "").strip()
    return ""


def _remote(post: PostBridgePost, results: list[PostBridgePostResult] = ()) -> RemotePost:
    return RemotePost(
        id=post.id,
        status=_STATUS[post.status],
        scheduled_at=post.scheduled_at,
        deliveries=tuple(
            Delivery(
                account_id=str(r.social_account_id),
                ok=r.success,
                url=(r.platform_data.url or "") if r.platform_data else "",
                error="" if r.success else _error_text(r.error),
            )
            for r in results
        ),
        warnings=tuple(w for w in post.warnings if w),
    )


def _reply_configs(replies: tuple[str, ...]) -> dict[str, dict] | None:
    """The first reply as a ``first_comment`` on every platform that posts
    one. Set per platform, so a cross-post to TikTok carries none."""
    first = next((r for r in replies if r.strip()), "")
    if not first:
        return None
    return {platform: {"first_comment": first} for platform in POSTBRIDGE.replies}


class PostBridgePublisher:
    spec = POSTBRIDGE

    def __init__(self, api_key: str, *, client: PostBridgeClient | None = None) -> None:
        self._pb = client or PostBridgeClient(api_key=api_key)

    async def __aenter__(self) -> PostBridgePublisher:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self._pb.aclose()

    async def list_accounts(self, platform: str | None = None) -> list[SocialAccount]:
        with _vendor():
            accounts = await self._pb.list_social_accounts(platform=platform, limit=_PAGE)
        # PostBridge returns no avatar and no connection health.
        return [SocialAccount(id=str(a.id), platform=a.platform.value, username=a.username) for a in accounts]

    async def upload(self, data: bytes, *, name: str, mime_type: str) -> MediaRef:
        with _vendor():
            upload = await self._pb.create_upload_url(name=name, mime_type=mime_type, size_bytes=len(data))
            await self._pb.upload_media(data, upload.upload_url, mime_type)
        return MediaRef(id=upload.media_id, mime_type=mime_type)

    async def create_post(self, post: Outgoing) -> RemotePost:
        configs = dict(_reply_configs(post.replies) or {})
        if post.tiktok_draft:
            configs["tiktok"] = {"draft": True}
        try:
            accounts = [int(t.account_id) for t in post.targets]
        except ValueError as exc:
            raise PublisherError("PostBridge account ids are numbers.", status_code=400) from exc
        with _vendor():
            resp = await self._pb.create_post(PostBridgeCreatePostRequest(
                caption=post.caption,
                social_accounts=accounts,
                media=[m.id for m in post.media] or None,
                scheduled_at=post.scheduled_at,
                platform_configurations=configs or None,
            ))
        return _remote(resp)

    async def get_post(self, post_id: str) -> RemotePost:
        with _vendor():
            post = await self._pb.get_post(post_id)
        if post.status == PostBridgePostStatus.SCHEDULED:
            return _remote(post)
        # Best effort: the post's status alone settles it, and post-results
        # is intermittently flaky on PostBridge's side.
        try:
            results = await self._pb.list_post_results(post_id=post_id, limit=10)
        except PostBridgeAPIError:
            results = []
        return _remote(post, results)

    async def update_words(self, remote: RemotePost, caption: str, replies: tuple[str, ...]) -> None:
        # An update without scheduled_at publishes at once (PostBridge's own
        # warning), so the time read back from PostBridge goes with every one.
        # A reply deleted after scheduling stays: the API documents no way to
        # clear a first_comment, so an update without one leaves it.
        with _vendor():
            await self._pb.update_post(remote.id, PostBridgeUpdatePostRequest(
                caption=caption,
                scheduled_at=remote.scheduled_at,
                platform_configurations=_reply_configs(replies),
            ))

    async def delete_post(self, post_id: str) -> None:
        try:
            await self._pb.delete_post(post_id)
        except PostBridgeAPIError as exc:
            # PostBridge answers 400 for a post it has already published.
            if exc.status_code == 400:
                raise PostAlreadyOut() from exc
            if exc.status_code != 404:
                raise PublisherError(exc.error.message or str(exc), status_code=exc.status_code) from exc

    async def fetch_metrics(self, post_id: str, *, platform: str, ref: str = "") -> PostMetrics | None:
        with _vendor():
            await self._pb.sync_analytics(platform=platform if platform in _SYNC_FILTERS else None)
            result_id = ref
            if not result_id:
                results = await self._pb.list_post_results(post_id=post_id, limit=10)
                if not results:
                    return None
                result_id = next((r for r in results if r.success), results[0]).id
            found = await self._pb.list_analytics(post_result_id=[result_id], limit=1)
        if not found:
            return None
        analytics = found[0]
        try:
            daily = (await self._pb.get_analytics_daily(analytics.id)).snapshots
        except PostBridgeAPIError:
            logger.info("post_bridge: no daily history for %s yet", analytics.id)
            daily = []
        return PostMetrics(
            ref=result_id,
            values=analytics.model_dump(mode="json"),
            synced_at=analytics.last_synced_at.isoformat() if analytics.last_synced_at else None,
            daily=tuple(s.model_dump(mode="json") for s in daily),
        )

    async def reported_posts(self, *, refresh: bool = False) -> list[ReportedPost]:
        records = []
        result_to_post: dict[str, str] = {}
        with _vendor():
            if refresh:
                await self._pb.sync_analytics()
            for page_no in range(_MAX_PAGES):
                page = await self._pb.list_analytics(limit=_PAGE, offset=page_no * _PAGE)
                records.extend(page)
                if len(page) < _PAGE:
                    break
            # Best effort: the result → post map is what ties a row to a Duct
            # post that only stored PostBridge's post id. Never fatal.
            try:
                result_to_post = {r.id: r.post_id for r in await self._pb.list_post_results(limit=_PAGE)}
            except PostBridgeAPIError:
                pass
        return [
            ReportedPost(
                ref=a.post_result_id,
                platform=a.platform or "",
                remote_post_id=result_to_post.get(a.post_result_id, ""),
                title=str(a.video_description or ""),
                url=str(a.share_url or ""),
                cover_url=str(a.cover_image_url or ""),
                views=a.view_count or 0,
                likes=a.like_count or 0,
                comments=a.comment_count or 0,
                shares=a.share_count or 0,
                posted_at=a.platform_created_at if isinstance(a.platform_created_at, str) else None,
                synced_at=a.last_synced_at.isoformat() if a.last_synced_at else None,
            )
            for a in records
        ]
