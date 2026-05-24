"""Async PostBridge HTTP client.

Every method returns a Pydantic model (or list thereof) — never a raw
dict. Non-2xx responses parse PostBridgeError and raise
PostBridgeAPIError so route handlers translate to clean HTTPExceptions.

Credentials live in ConnectorCredential rows (connector_type='post_bridge').
The helper client_for_user(user_id, db) does the decrypt + client build.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlmodel import Session

from models.connector import ConnectorCredential
from service.credentials import decrypt_credentials
from service.post_bridge.schema import (
    PostBridgeAnalytics,
    PostBridgeCreatePostRequest,
    PostBridgeCreatePostResponse,
    PostBridgeDailySnapshot,
    PostBridgeError,
    PostBridgePost,
    PostBridgeSocialAccount,
    PostBridgeUploadUrl,
)

logger = logging.getLogger(__name__)


_DEFAULT_BASE_URL = "https://api.post-bridge.com"
_DEFAULT_TIMEOUT  = httpx.Timeout(30.0, connect=10.0)
_USER_AGENT       = "DuctContentAgent/1.0 (+https://getduct.ai)"


class PostBridgeAPIError(RuntimeError):
    """Raised on any non-2xx response. Wraps a PostBridgeError."""

    def __init__(self, error: PostBridgeError, *, status_code: int, url: str):
        self.error       = error
        self.status_code = status_code
        self.url         = url
        super().__init__(f"PostBridge {status_code} on {url}: {error.code or '?'} — {error.message}")


class PostBridgeClient:
    """httpx.AsyncClient-backed PostBridge client.

    Construct via client_for_user() in routes; tests can instantiate
    directly with a fake api_key + base_url pointing at a local server.
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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
        params: dict | None = None,
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
            err = PostBridgeError.model_validate(body) if isinstance(body, dict) else PostBridgeError(message=str(body))
            logger.warning("post_bridge: %s %s → %s %s", method, url, resp.status_code, err.message)
            raise PostBridgeAPIError(err, status_code=resp.status_code, url=url)

        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    async def list_social_accounts(
        self,
        platform: str | None = None,
    ) -> list[PostBridgeSocialAccount]:
        params = {"platform": platform} if platform else None
        data = await self._request("GET", "/v1/social-accounts", params=params)
        items = data.get("items", data) if isinstance(data, dict) else data
        return [PostBridgeSocialAccount.model_validate(x) for x in items]

    async def create_upload_url(self) -> PostBridgeUploadUrl:
        data = await self._request("POST", "/v1/media/create-upload-url")
        return PostBridgeUploadUrl.model_validate(data)

    async def upload_media(
        self,
        file_bytes: bytes,
        upload_url: str,
        content_type: str,
    ) -> None:
        """PUT bytes at the signed URL returned by create_upload_url.

        Uses a separate request (no auth header — the URL is pre-signed).
        Raises PostBridgeAPIError on non-2xx.
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

    async def create_post(
        self,
        request: PostBridgeCreatePostRequest,
    ) -> PostBridgeCreatePostResponse:
        data = await self._request(
            "POST",
            "/v1/posts",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        return PostBridgeCreatePostResponse.model_validate(data)

    async def get_analytics(self, post_id: str) -> PostBridgeAnalytics:
        data = await self._request("GET", f"/v1/posts/{post_id}/analytics")
        # Some PostBridge responses omit post_id in the body; backfill from path.
        if isinstance(data, dict) and "post_id" not in data:
            data["post_id"] = post_id
        return PostBridgeAnalytics.model_validate(data)

    async def get_daily_analytics(
        self,
        post_id: str,
        *,
        since: date | None = None,
    ) -> list[PostBridgeDailySnapshot]:
        params = {"since": since.isoformat()} if since else None
        data = await self._request(
            "GET",
            f"/v1/posts/{post_id}/analytics/daily",
            params=params,
        )
        items = data.get("items", data) if isinstance(data, dict) else data
        return [PostBridgeDailySnapshot.model_validate(x) for x in items]

    async def list_posts(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[PostBridgePost], str | None]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        data = await self._request("GET", "/v1/posts", params=params)
        items = data.get("items", data) if isinstance(data, dict) else data
        next_cursor = data.get("next_cursor") if isinstance(data, dict) else None
        return [PostBridgePost.model_validate(x) for x in items], next_cursor


# ---------------------------------------------------------------------------
# Credential resolver
# ---------------------------------------------------------------------------


def client_for_user(user_id: UUID, db: Session) -> PostBridgeClient:
    """Build a PostBridgeClient using the user's stored connector credential.

    Looks up ConnectorCredential where connector_type='post_bridge' and
    user_id matches; decrypts the api_key; constructs the client.

    Raises ValueError if no credential exists — the route layer should
    translate that to a 400/404 with a "connect PostBridge first" message.
    """
    row = db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user_id,
            ConnectorCredential.connector_type == "post_bridge",
        )
    ).scalars().first()
    if row is None:
        raise ValueError(
            "PostBridge is not connected for this user. Add an API key in "
            "Settings → Connectors first."
        )
    creds = decrypt_credentials(row.credentials_enc)
    api_key = creds.get("api_key") or creds.get("token") or ""
    if not api_key:
        raise ValueError("PostBridge credential is missing 'api_key'.")
    base_url = creds.get("base_url") or _DEFAULT_BASE_URL
    return PostBridgeClient(api_key=api_key, base_url=base_url)
