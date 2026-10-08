"""Async client for the PostBridge v1 API.

Wraps every endpoint we use, returning Pydantic models from schema.py.
Non-2xx responses raise PostBridgeAPIError carrying a parsed
PostBridgeError so route handlers can translate to clean HTTPExceptions.

Auth: each user's own PostBridge API key (``POSTBRIDGE_KEY`` below, and
service/vendor_keys.py for why a hosted instance never spends its own).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlmodel import Session

from service.vendor_keys import VendorKey, VendorKeyRejected, VendorKeyUnchecked
from service.post_bridge.schema import (
    CreateUploadUrlRequest,
    PostBridgeAnalytics,
    PostBridgeAnalyticsDaily,
    PostBridgeCreatePostRequest,
    PostBridgeError,
    PostBridgePost,
    PostBridgePostResult,
    PostBridgeSocialAccount,
    PostBridgeUpdatePostRequest,
    PostBridgeUploadUrl,
)

logger = logging.getLogger(__name__)


_DEFAULT_BASE_URL = "https://api.post-bridge.com"
_DEFAULT_TIMEOUT  = httpx.Timeout(30.0, connect=10.0)
_USER_AGENT       = "DuctContentAgent/1.0 (+https://getduct.ai)"


class PostBridgeAPIError(RuntimeError):
    """Raised on any non-2xx (or transport) response. Wraps PostBridgeError."""

    def __init__(self, error: PostBridgeError, *, status_code: int, url: str):
        self.error       = error
        self.status_code = status_code
        self.url         = url
        super().__init__(
            f"PostBridge {status_code} on {url}: "
            f"{error.code or '?'} — {error.message}"
        )


class PostBridgeClient:
    """Async PostBridge client. Designed for use as `async with`.

    Tests can pass an httpx.AsyncClient with a MockTransport for unit
    coverage; route handlers should use client_for_user() to pick up
    the user's credential.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: httpx.Timeout | float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("PostBridgeClient: api_key is required")
        self._api_key  = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout  = timeout if timeout is not None else _DEFAULT_TIMEOUT
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            trust_env=False,
        )

    async def __aenter__(self) -> PostBridgeClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Low-level
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent":    _USER_AGENT,
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | list | None = None,
        json:   dict | None = None,
    ) -> dict | list:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.request(
                method, url,
                params=params,
                json=json,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            logger.warning("post_bridge: network error on %s %s: %s", method, url, exc)
            raise PostBridgeAPIError(
                PostBridgeError(code="network_error", message=str(exc)),
                status_code=0,
                url=url,
            ) from exc

        if resp.status_code >= 400:
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {"message": resp.text[:400]}
            # An error body we cannot read must still be an error about
            # PostBridge, never our own 500.
            try:
                err = (
                    PostBridgeError.model_validate(body)
                    if isinstance(body, dict)
                    else PostBridgeError(message=str(body)[:400])
                )
            except ValidationError:
                err = PostBridgeError(message=str(body)[:400])
            logger.warning(
                "post_bridge: %s %s → %s %s",
                method, url, resp.status_code, err.message,
            )
            raise PostBridgeAPIError(err, status_code=resp.status_code, url=url)

        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    @staticmethod
    def _items(body: dict | list) -> list:
        """Unwrap `{ data: [...] }` envelope, else return the raw list."""
        if isinstance(body, dict) and "data" in body:
            return body["data"] or []
        if isinstance(body, list):
            return body
        return []

    # ------------------------------------------------------------------
    # Social accounts
    # ------------------------------------------------------------------

    async def list_social_accounts(
        self,
        *,
        platform: str | list[str] | None = None,
        username: str | list[str] | None = None,
        limit: int = 50,
    ) -> list[PostBridgeSocialAccount]:
        params: list[tuple[str, str]] = [("limit", str(limit))]
        if platform:
            for p in (platform if isinstance(platform, list) else [platform]):
                params.append(("platform", p))
        if username:
            for u in (username if isinstance(username, list) else [username]):
                params.append(("username", u))
        body = await self._request("GET", "/v1/social-accounts", params=params)
        return [PostBridgeSocialAccount.model_validate(x) for x in self._items(body)]

    # ------------------------------------------------------------------
    # Media upload
    # ------------------------------------------------------------------

    async def create_upload_url(
        self, *, name: str, mime_type: str, size_bytes: int,
    ) -> PostBridgeUploadUrl:
        req = CreateUploadUrlRequest(name=name, mime_type=mime_type, size_bytes=size_bytes)
        body = await self._request(
            "POST", "/v1/media/create-upload-url",
            json=req.model_dump(mode="json"),
        )
        return PostBridgeUploadUrl.model_validate(body)

    async def upload_media(
        self,
        file_bytes: bytes,
        upload_url: str,
        content_type: str,
    ) -> None:
        """PUT bytes at the signed URL returned by create_upload_url.

        Uses a separate request without the Authorization header — the URL
        is pre-signed. Raises PostBridgeAPIError on non-2xx.
        """
        try:
            resp = await self._client.put(
                upload_url,
                content=file_bytes,
                headers={"Content-Type": content_type, "User-Agent": _USER_AGENT},
            )
        except httpx.HTTPError as exc:
            raise PostBridgeAPIError(
                PostBridgeError(code="network_error", message=str(exc)),
                status_code=0,
                url=upload_url,
            ) from exc
        if resp.status_code >= 400:
            raise PostBridgeAPIError(
                PostBridgeError(code="upload_failed", message=resp.text[:400]),
                status_code=resp.status_code,
                url=upload_url,
            )

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    async def create_post(
        self,
        request: PostBridgeCreatePostRequest,
    ) -> PostBridgePost:
        body = await self._request(
            "POST", "/v1/posts",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        return PostBridgePost.model_validate(body)

    async def get_post(self, post_id: str) -> PostBridgePost:
        body = await self._request("GET", f"/v1/posts/{post_id}")
        return PostBridgePost.model_validate(body)

    async def update_post(
        self, post_id: str, request: PostBridgeUpdatePostRequest,
    ) -> PostBridgePost:
        body = await self._request(
            "PATCH", f"/v1/posts/{post_id}",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        return PostBridgePost.model_validate(body)

    async def delete_post(self, post_id: str) -> None:
        """Only a scheduled or draft post can be deleted; PostBridge answers
        400 for one it has already published."""
        await self._request("DELETE", f"/v1/posts/{post_id}")

    async def list_posts(
        self,
        *,
        platform: list[str] | None = None,
        status:   list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PostBridgePost], int | None]:
        params: list[tuple[str, str]] = [("limit", str(limit)), ("offset", str(offset))]
        for p in platform or []:
            params.append(("platform", p))
        for s in status or []:
            params.append(("status", s))
        body = await self._request("GET", "/v1/posts", params=params)
        items = [PostBridgePost.model_validate(x) for x in self._items(body)]
        meta = body.get("meta") if isinstance(body, dict) else None
        next_offset = None
        if isinstance(meta, dict) and meta.get("next"):
            next_offset = offset + limit
        return items, next_offset

    # ------------------------------------------------------------------
    # Post results — the bridge between a post and analytics
    # ------------------------------------------------------------------

    async def list_post_results(
        self,
        *,
        post_id: str | None = None,
        platform: list[str] | None = None,
        limit: int = 50,
    ) -> list[PostBridgePostResult]:
        params: list[tuple[str, str]] = [("limit", str(limit))]
        if post_id:
            params.append(("post_id", post_id))
        for p in platform or []:
            params.append(("platform", p))
        body = await self._request("GET", "/v1/post-results", params=params)
        return [PostBridgePostResult.model_validate(x) for x in self._items(body)]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    async def sync_analytics(self, platform: str | None = None) -> None:
        """POST /v1/analytics/sync — kick PostBridge to fetch fresh numbers.

        Ignores 429 (rate-limited) silently because the docs say to wait
        between syncs; calling sync isn't required before reading analytics.
        """
        params = {"platform": platform} if platform else None
        try:
            await self._request("POST", "/v1/analytics/sync", params=params)
        except PostBridgeAPIError as exc:
            if exc.status_code == 429:
                logger.info("post_bridge: analytics sync rate-limited (ok, reading cached)")
                return
            raise

    async def list_analytics(
        self,
        *,
        post_result_id: list[str] | None = None,
        platform: str | None = None,
        timeframe: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PostBridgeAnalytics]:
        params: list[tuple[str, str]] = [("limit", str(limit)), ("offset", str(offset))]
        for rid in post_result_id or []:
            params.append(("post_result_id", rid))
        if platform:
            params.append(("platform", platform))
        if timeframe:
            params.append(("timeframe", timeframe))
        body = await self._request("GET", "/v1/analytics", params=params)
        return [PostBridgeAnalytics.model_validate(x) for x in self._items(body)]

    async def get_analytics(self, analytics_id: str) -> PostBridgeAnalytics:
        body = await self._request("GET", f"/v1/analytics/{analytics_id}")
        return PostBridgeAnalytics.model_validate(body)

    async def get_analytics_daily(self, analytics_id: str) -> PostBridgeAnalyticsDaily:
        body = await self._request("GET", f"/v1/analytics/{analytics_id}/daily")
        return PostBridgeAnalyticsDaily.model_validate(body)


# ---------------------------------------------------------------------------
# Credential resolver
# ---------------------------------------------------------------------------


async def check_api_key(api_key: str) -> None:
    """Listing one account is the cheapest read that proves a key works."""
    try:
        async with PostBridgeClient(api_key=api_key) as pb:
            await pb.list_social_accounts(limit=1)
    except PostBridgeAPIError as exc:
        if exc.status_code in (401, 403):
            raise VendorKeyRejected() from exc
        raise VendorKeyUnchecked() from exc


POSTBRIDGE_KEY = VendorKey(
    connector_type="post_bridge",
    setting="postbridge_api_key",
    label="PostBridge",
    where="Connections or Content → Accounts",
    check=check_api_key,
)


def client_for_user(user_id: UUID, db: Session) -> PostBridgeClient:
    """A client on the key ``user_id`` may spend (service/vendor_keys.py)."""
    return PostBridgeClient(api_key=POSTBRIDGE_KEY.resolve(user_id, db))
