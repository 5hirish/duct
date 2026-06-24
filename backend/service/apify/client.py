"""Async Apify v2 client for the TikTok content-discovery flow.

Endpoints we wrap (https://docs.apify.com/api/v2):
  - POST /v2/acts/{actorId}/runs                 — start an actor run
  - GET  /v2/actor-runs/{runId}                  — poll status
  - GET  /v2/datasets/{datasetId}/items          — fetch dataset items

Designed for use as `async with ApifyClient(api_key) as client: ...`.
Mirrors service/post_bridge/client.py patterns (pool, timeouts, UA
header, structured error raising).
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from service.apify.schema import ApifyRun, ScrapedPost

logger = logging.getLogger(__name__)


_DEFAULT_BASE_URL = "https://api.apify.com"
_DEFAULT_TIMEOUT  = httpx.Timeout(60.0, connect=10.0)
_USER_AGENT       = "DuctContentAgent/1.0 (+https://getduct.ai)"
_APIFY_ID_RE      = re.compile(r"^[A-Za-z0-9_~/-]+$")


class ApifyAPIError(RuntimeError):
    """Raised on non-2xx responses from Apify. Carries the parsed error body."""

    def __init__(self, status_code: int, url: str, message: str = ""):
        self.status_code = status_code
        self.url         = url
        self.message     = message or f"Apify {status_code}"
        super().__init__(f"Apify {status_code} on {url}: {self.message}")


def _validate_id(value: str, label: str) -> str:
    """Defense against URL-injection through actor / run / dataset IDs.

    Apify IDs are alphanumeric + a handful of safe chars (e.g. `_~/-`).
    We block everything else before interpolating into the URL.
    """
    if not isinstance(value, str) or not value or not _APIFY_ID_RE.match(value):
        raise ValueError(f"invalid {label}: {value!r}")
    return value


class ApifyClient:
    """Async Apify client. Use as `async with`."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: httpx.Timeout | float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ApifyClient: api_key is required")
        self._api_key  = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout  = timeout if timeout is not None else _DEFAULT_TIMEOUT
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "User-Agent":    _USER_AGENT,
                "Accept":        "application/json",
            },
        )

    async def __aenter__(self) -> "ApifyClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise ApifyAPIError(0, url, f"transport: {exc}") from exc
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("error", {}).get("message") or body.get("message") or resp.text[:200]
            except ValueError:
                msg = resp.text[:200]
            raise ApifyAPIError(resp.status_code, url, message=msg)
        return resp

    async def start_run(self, actor_id: str, input_payload: dict[str, Any]) -> ApifyRun:
        """Start an actor run. Returns the run object including
        defaultDatasetId so the caller can poll → fetch items later."""
        actor_id = _validate_id(actor_id, "actor_id")
        # Apify's API addresses store actors as `username~actorName`, but the
        # Store/UI shows them as `username/actorName`. A literal `/` becomes an
        # extra URL path segment, which Apify answers with a 404 ("there is no
        # API endpoint at this URL"). Normalize the slug to the tilde form.
        slug = actor_id.replace("/", "~")
        path = f"/v2/acts/{quote(slug, safe='~_-')}/runs"
        resp = await self._request("POST", path, json=input_payload)
        try:
            return ApifyRun.model_validate((resp.json() or {}).get("data") or {})
        except ValidationError as exc:
            raise ApifyAPIError(500, path, f"invalid run payload: {exc}") from exc

    async def get_run(self, run_id: str) -> ApifyRun:
        run_id = _validate_id(run_id, "run_id")
        path = f"/v2/actor-runs/{run_id}"
        resp = await self._request("GET", path)
        try:
            return ApifyRun.model_validate((resp.json() or {}).get("data") or {})
        except ValidationError as exc:
            raise ApifyAPIError(500, path, f"invalid run payload: {exc}") from exc

    async def get_dataset_items(
        self,
        dataset_id: str,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch raw items from a dataset. Returns list of dicts —
        the caller can model them via ScrapedPost when appropriate.
        """
        dataset_id = _validate_id(dataset_id, "dataset_id")
        clean_limit  = max(1, min(int(limit),  1000))
        clean_offset = max(0, int(offset))
        path  = f"/v2/datasets/{dataset_id}/items"
        params = {"limit": clean_limit, "offset": clean_offset, "clean": "true"}
        resp = await self._request("GET", path, params=params)
        try:
            return resp.json() or []
        except ValueError as exc:
            raise ApifyAPIError(500, path, f"invalid items payload: {exc}") from exc

    async def get_dataset_posts(
        self,
        dataset_id: str,
        *,
        limit: int = 500,
    ) -> list[ScrapedPost]:
        """Like get_dataset_items but validates each item via ScrapedPost.
        Bad items are dropped (the actor evolves; we don't want one weird row
        to bork the whole discovery flow) — but loudly: a silent drop once
        masked an actor field-shape change (hashtags str→object) as a total
        "couldn't fetch this TikTok", so log at WARNING with the field errors
        so the next drift is visible, not invisible."""
        items = await self.get_dataset_items(dataset_id, limit=limit)
        posts: list[ScrapedPost] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            try:
                posts.append(ScrapedPost.model_validate(raw))
            except ValidationError as exc:
                fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors()[:5])
                logger.warning(
                    "apify: dropped invalid item (id=%r) — %d validation error(s) on: %s",
                    raw.get("id"), len(exc.errors()), fields,
                )
                continue
        return posts


# ---------------------------------------------------------------------------
# Convenience: the two MVP actor IDs the Discover page exposes.
# ---------------------------------------------------------------------------


def get_default_actor_ids() -> dict[str, str]:
    """Hard-coded default Apify actors for MVP discovery flow.

    POST_BY_HASHTAG fetches recent top posts for hashtag(s); TREND_FEED
    fetches trending posts in a region. Override via env in the future
    when we expose this as a per-project config.
    """
    return {
        "post_by_hashtag": "clockworks/tiktok-scraper",
        "trend_feed":      "clockworks/free-tiktok-scraper",
    }
