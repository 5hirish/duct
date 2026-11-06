"""Async client for the Zernio v1 API (https://docs.zernio.com).

Only the calls a scheduler needs: accounts, media, posts and their numbers.
Async with a long-lived ``httpx.AsyncClient``, like ``service/post_bridge``,
rather than ``service/rest.py``: a publish is a short chain of dependent
calls, and a retried create could post twice. Creates carry an
``Idempotency-Key`` for exactly that reason, so a retry inside Zernio's 24
hours returns the first post rather than a second one.

Auth: each user's own Zernio key (``ZERNIO_KEY``); ``ZERNIO_API_KEY`` is a
local and desktop fallback only (service/vendor_keys.py).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import ValidationError

from service.vendor_keys import VendorKey, VendorKeyRejected, VendorKeyUnchecked
from service.zernio.schema import (
    ZernioAccount,
    ZernioAnalyticsPost,
    ZernioError,
    ZernioPost,
    ZernioPostAnswer,
    ZernioPresign,
    ZernioTimelineDay,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://zernio.com/api/v1"
_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_USER_AGENT = "DuctContentAgent/1.0 (+https://getduct.ai)"

# 202: a post's numbers are still syncing from the platform.
SYNC_PENDING = 202


class ZernioAPIError(RuntimeError):
    """Any non-2xx answer, or no answer at all (``status_code`` 0)."""

    def __init__(self, error: ZernioError, *, status_code: int, url: str) -> None:
        self.error = error
        self.status_code = status_code
        self.url = url
        super().__init__(f"Zernio {status_code} on {url}: {error.code or error.type or '?'}: {error.error}")


class ZernioClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ZernioClient: api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True, trust_env=False)

    async def __aenter__(self) -> ZernioClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[int, dict]:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.request(
                method, url, params=params, json=json,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                    **(headers or {}),
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("zernio: network error on %s %s: %s", method, url, exc)
            raise ZernioAPIError(ZernioError(code="network_error", error=str(exc)), status_code=0, url=url) from exc
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {"error": resp.text[:400]}
        if resp.status_code >= 400:
            try:
                err = ZernioError.model_validate(body) if isinstance(body, dict) else ZernioError(error=str(body)[:400])
            except ValidationError:
                err = ZernioError(error=str(body)[:400])
            logger.warning("zernio: %s %s → %s %s", method, url, resp.status_code, err.code or err.error)
            raise ZernioAPIError(err, status_code=resp.status_code, url=url)
        return resp.status_code, body if isinstance(body, dict) else {}

    # -- accounts ------------------------------------------------------------

    async def list_accounts(self, *, platform: str | None = None) -> list[ZernioAccount]:
        params = {"platform": platform} if platform else None
        _, body = await self._request("GET", "/accounts", params=params)
        return [ZernioAccount.model_validate(a) for a in body.get("accounts") or []]

    # -- media ---------------------------------------------------------------

    async def presign(self, *, filename: str, content_type: str, size: int) -> ZernioPresign:
        _, body = await self._request("POST", "/media/presign", json={
            "filename": filename, "contentType": content_type, "size": size,
        })
        return ZernioPresign.model_validate(body)

    async def put_file(self, upload_url: str, data: bytes, content_type: str) -> None:
        """PUT the bytes at the presigned URL. No Authorization header: the
        URL carries its own."""
        try:
            resp = await self._client.put(upload_url, content=data, headers={"Content-Type": content_type})
        except httpx.HTTPError as exc:
            raise ZernioAPIError(ZernioError(code="network_error", error=str(exc)), status_code=0, url=upload_url) from exc
        if resp.status_code >= 400:
            raise ZernioAPIError(
                ZernioError(code="upload_failed", error=resp.text[:400]), status_code=resp.status_code, url=upload_url,
            )

    # -- posts ---------------------------------------------------------------

    async def create_post(self, body: dict, *, idempotency_key: str) -> ZernioPostAnswer:
        # 207 (some platforms failed an immediate publish) is a 2xx and
        # carries the post; its platform entries say which.
        _, answer = await self._request("POST", "/posts", json=body, headers={"Idempotency-Key": idempotency_key})
        return ZernioPostAnswer.model_validate(answer)

    async def get_post(self, post_id: str) -> ZernioPost:
        _, body = await self._request("GET", f"/posts/{post_id}")
        return ZernioPost.model_validate(body.get("post") or body)

    async def update_post(self, post_id: str, body: dict) -> ZernioPostAnswer:
        _, answer = await self._request("PUT", f"/posts/{post_id}", json=body)
        return ZernioPostAnswer.model_validate(answer)

    async def delete_post(self, post_id: str) -> None:
        await self._request("DELETE", f"/posts/{post_id}")

    # -- analytics -------------------------------------------------------------

    async def post_analytics(self, post_id: str) -> ZernioAnalyticsPost | None:
        """A post's numbers, or None while Zernio is still syncing them (202)."""
        status, body = await self._request("GET", "/analytics", params={"postId": post_id})
        if status == SYNC_PENDING:
            return None
        return ZernioAnalyticsPost.model_validate(body)

    async def list_analytics(self, *, page: int = 1, limit: int = 100) -> tuple[list[ZernioAnalyticsPost], int]:
        """One page of the account's posts with their numbers, and how many
        pages there are."""
        _, body = await self._request("GET", "/analytics", params={"page": page, "limit": limit})
        posts = [ZernioAnalyticsPost.model_validate(p) for p in body.get("posts") or []]
        return posts, int((body.get("pagination") or {}).get("pages") or 1)

    async def post_timeline(self, post_id: str) -> list[ZernioTimelineDay]:
        _, body = await self._request("GET", "/analytics/post-timeline", params={"postId": post_id})
        return [ZernioTimelineDay.model_validate(d) for d in body.get("timeline") or []]


async def check_api_key(api_key: str) -> None:
    """Listing the accounts is the cheapest read that proves a key works."""
    try:
        async with ZernioClient(api_key) as client:
            await client.list_accounts()
    except ZernioAPIError as exc:
        if exc.status_code in (401, 403):
            raise VendorKeyRejected() from exc
        raise VendorKeyUnchecked() from exc


ZERNIO_KEY = VendorKey(
    connector_type="zernio",
    setting="zernio_api_key",
    label="Zernio",
    where="Content → Accounts",
    check=check_api_key,
)
