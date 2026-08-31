"""GrowthBook REST API v1 — experimentation truth, read-only.

The engagement read GrowthBook through its MCP server and found both live
experiments had silently stopped bucketing users for 74 days while still
showing "running" — nothing in the platform flags it. That is the trap this
connector exists to surface: an experiment's status is a setting, not a
signal. Exposure has to be checked against the analysis dates.

Auth: an API key (``secret_…``) from Settings → API Keys, sent as Bearer.
Read-only keys are enough; Duct never writes here — flag flips are product
decisions, not marketing execution. Self-hosted deployments override
``base_url``.

Pagination is limit/offset with ``hasMore`` + ``nextOffset`` in every list
envelope; the list key is the plural resource name (``experiments``,
``features`` …).
"""

from __future__ import annotations

import json

from service.rest import Endpoint, RetryPolicy
from service.rest import ApiError as BaseApiError

DEFAULT_API_BASE = "https://api.growthbook.io/api/v1"
API_VERSION = "growthbook-v1"
PAGE_LIMIT = 100


class ApiError(BaseApiError):
    def parse(self, body: str) -> str:
        try:
            data = json.loads(body)
        except Exception:  # noqa: BLE001
            return ""
        if isinstance(data, dict):
            return str(data.get("message") or data.get("error") or "")
        return ""

    def hint(self) -> str:
        if self.status in (401, 403):
            return (
                "GrowthBook rejected the API key. Create one at Settings → API Keys "
                "(a read-only key is enough) and, for self-hosted GrowthBook, set base_url."
            )
        return ""


def require_credentials(creds: dict[str, str]) -> str:
    key = (creds.get("api_key") or "").strip()
    if not key:
        raise ValueError(
            "GrowthBook credentials incomplete — api_key missing. Create one at "
            "Settings → API Keys; a read-only key is enough."
        )
    return key


def base_url(creds: dict[str, str]) -> str:
    raw = (creds.get("base_url") or "").strip().rstrip("/")
    if not raw:
        return DEFAULT_API_BASE
    return raw if raw.endswith("/api/v1") else f"{raw}/api/v1"


_ENDPOINTS: dict[str, Endpoint] = {}


def _endpoint(creds: dict[str, str]) -> Endpoint:
    root = base_url(creds)
    endpoint = _ENDPOINTS.get(root)
    if endpoint is None:
        endpoint = Endpoint(
            base_url=root,
            error_cls=ApiError,
            retry=RetryPolicy(attempts=4, first=1.0, cap=20.0),
            timeout=60,
            success=frozenset({200}),
        )
        _ENDPOINTS[root] = endpoint
    return endpoint


def api(path: str, creds: dict[str, str], params: dict | None = None) -> dict:
    key = require_credentials(creds)
    return _endpoint(creds).request(
        path, params=params, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}
    )


def get_all(path: str, list_key: str, creds: dict[str, str], params: dict | None = None, cap: int = 500) -> list:
    """Follow limit/offset until ``hasMore`` is false (or ``cap`` rows)."""
    rows: list = []
    offset = 0
    while True:
        page = api(path, creds, dict(params or {}, limit=PAGE_LIMIT, offset=offset))
        batch = list(page.get(list_key) or [])
        rows.extend(batch)
        if len(rows) >= cap or not page.get("hasMore") or not batch:
            return rows[:cap]
        offset = int(page.get("nextOffset") or (offset + len(batch)))
