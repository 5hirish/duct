"""Microsoft Clarity Data Export API — landing-page friction, read-only.

The engagement filed Clarity as "UI only (no useful API)". Clarity has since
shipped a Data Export API, and it is worth having because it answers the one
question the ad platforms cannot: what happens to paid traffic *after* the
click — rage clicks, dead clicks, quick-backs, script errors, per landing
page. It is deliberately tiny and tightly budgeted, so the rules are:

- **10 requests per project per day.** ``list_accounts`` spends one to verify
  the token; a pull spends two (overall + per-URL). There is no way to buy
  more — a 429 here means "tomorrow", and it is NOT retried.
- **Only the last 1–3 days.** ``numOfDays`` caps at 3. This is a live-health
  signal, not a history source; trend it by pulling daily.
- Up to three dimensions per call (Browser, Device, Country/Region, OS,
  Source, Medium, Campaign, Channel, URL).

Auth: a project-scoped API token generated at Clarity → Settings → Data
Export → Generate new API token. The token IS the project selector — there
is no project id in the request.
"""

from __future__ import annotations

import json
from typing import Any

from service.rest import Endpoint, RetryPolicy
from service.rest import ApiError as BaseApiError

API_BASE = "https://www.clarity.ms/export-data/api/v1"
API_VERSION = "export-data-v1"
DAILY_REQUEST_BUDGET = 10
MAX_DAYS = 3
DIMENSIONS = ("Browser", "Device", "Country/Region", "OS", "Source", "Medium", "Campaign", "Channel", "URL")


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
                "Clarity rejected the API token. Generate one at Clarity → Settings → "
                "Data Export → Generate new API token, and paste it whole."
            )
        if self.status == 429:
            return (
                f"Clarity's Data Export API allows {DAILY_REQUEST_BUDGET} requests per "
                "project per day — the budget is spent until tomorrow."
            )
        return ""


def require_credentials(creds: dict[str, str]) -> str:
    token = (creds.get("api_token") or "").strip()
    if not token:
        raise ValueError(
            "Clarity credentials incomplete — api_token missing. Generate one at "
            "Clarity → Settings → Data Export → Generate new API token."
        )
    return token


# 429 is a daily budget, not a throttle — retrying burns nothing but must
# not be attempted. Only transient 5xx get a second try.
_ENDPOINT = Endpoint(
    base_url=API_BASE,
    error_cls=ApiError,
    retry=RetryPolicy(attempts=2, statuses={500, 502, 503, 504}, first=2.0, cap=4.0),
    timeout=60,
    success=frozenset({200}),
)


def live_insights(
    creds: dict[str, str], num_days: int = 1, dimensions: list[str] | None = None
) -> list[dict[str, Any]]:
    """One ``project-live-insights`` call. Returns the raw metric list."""
    token = require_credentials(creds)
    params: dict[str, Any] = {"numOfDays": max(1, min(int(num_days or 1), MAX_DAYS))}
    for idx, dim in enumerate((dimensions or [])[:3], start=1):
        if dim not in DIMENSIONS:
            raise ValueError(f"Unknown Clarity dimension {dim!r}. Choose from: {', '.join(DIMENSIONS)}")
        params[f"dimension{idx}"] = dim
    data = _ENDPOINT.request(
        "project-live-insights",
        params=params,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if isinstance(data, list):
        return data
    return list(data.get("results") or data.get("data") or [])
