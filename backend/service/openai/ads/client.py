"""OpenAI Ads (ChatGPT Ads) Advertiser API v1 — auth + transport.

Ported from Gads ``openai_ads_common.py`` (curl → httpx).

Auth is the simplest of the five — no OAuth exists at all:
    an Ads API key from Ads Manager → Settings → Authorization: Bearer <key>
The key is **scoped to a single ad account**, so there is no account-id
parameter anywhere: GET /ad_account tells you which one you are pointed at.

⚠ THE BIG CAVEAT — insights cannot see conversions. The metric set is exactly
impressions, clicks, spend, ctr, cpc, cpm. Pixel conversions are visible only
in the Ads Manager UI. Never present CPC as the decision metric for a channel
whose job is paid signups.

⚠ UNITS DIFFER FROM THE PIXEL: insights ``spend`` is a decimal in account
currency (18.42); the measurement pixel's ``amount`` is an integer in MINOR
units (1499). Same vendor, opposite conventions — see pixel_amount().
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, timedelta
from typing import Any

import httpx

API_BASE = "https://api.ads.openai.com/v1"

# Documented limits: 600 req/min per endpoint, 1200 req/min overall — nowhere
# near binding for a reporting pull, but keep a floor between calls.
MIN_INTERVAL = 0.2

INSIGHT_METRICS = ["impressions", "clicks", "spend", "ctr", "cpc", "cpm"]
AGGREGATION_LEVELS = ["ad_account", "campaign", "ad_group", "ad"]


class ApiError(Exception):
    def __init__(self, code: int, body: str, url: str = ""):
        self.code = code
        self.body = body
        self.url = url
        self.detail = self._parse(body)
        super().__init__(f"HTTP {code} — {self.detail or (body or '')[:200]}")

    @staticmethod
    def _parse(body: str) -> str:
        try:
            err = json.loads(body).get("error", {})
            if isinstance(err, str):
                return err
            return err.get("message") or err.get("code") or ""
        except (ValueError, AttributeError):
            return ""

    def hint(self) -> str:
        if self.code == 401:
            return ("Key rejected. Ads Manager → Settings → API keys; a key is "
                    "scoped to ONE ad account, so a key from another account 401s.")
        if self.code == 404 and "conversions" in self.url:
            return ("Pixel/Conversions-API management is not enabled for this ad "
                    "account (partner-gated). The pixel still works; only API "
                    "management is gated.")
        if self.code == 429:
            return "Rate limited (600/min per endpoint, 1200/min overall)."
        return ""


def require_credentials(creds: dict[str, str]) -> str:
    key = (creds.get("api_key") or "").strip()
    if not key:
        raise ValueError(
            "OpenAI Ads credentials incomplete — api_key missing. Issue one at "
            "ads.openai.com → Settings → API keys (a key is scoped to ONE ad "
            "account — make sure it is the right one)."
        )
    return key


def _encode(params: dict | None) -> list[tuple[str, str]]:
    """Query pairs with repeated keys for the []-suffixed array params.

    ``fields[]``, ``filters[]``, ``sort[]``, ``segments[]``, ``time_ranges[]``
    are repeated-key arrays, not comma lists; dict values become JSON."""
    flat: list[tuple[str, str]] = []
    for k, v in (params or {}).items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            flat += [(k, json.dumps(i, separators=(",", ":")) if isinstance(i, dict) else str(i))
                     for i in v]
        else:
            flat.append((k, str(v)))
    return flat


_last_call = [0.0]
_pace_lock = threading.Lock()


def api(path: str, creds: dict[str, str], params: dict | None = None,
        retries: int = 4, payload: dict | None = None) -> dict:
    """GET (or POST when ``payload`` is given) against the Ads API."""
    key = require_credentials(creds)
    url = f"{API_BASE}/{path.lstrip('/')}"

    with _pace_lock:
        gap = time.time() - _last_call[0]
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_call[0] = time.time()

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    for attempt in range(retries):
        try:
            if payload is not None:
                resp = httpx.post(url, params=_encode(params), json=payload,
                                  headers=headers, timeout=180)
            else:
                resp = httpx.get(url, params=_encode(params), headers=headers, timeout=180)
        except httpx.HTTPError as exc:
            if attempt == retries - 1:
                raise ApiError(0, f"request failed: {exc}", url) from exc
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        raise ApiError(resp.status_code, resp.text, url)
    raise ApiError(0, "retries exhausted", url)


def get_all(path: str, creds: dict[str, str], params: dict | None = None,
            limit: int = 500, cap: int | None = None) -> list:
    """Follow `after`/`last_id` cursors until has_more is false."""
    params = dict(params or {})
    params["limit"] = limit
    rows: list = []
    after: str | None = None
    while True:
        if after:
            params["after"] = after
        page = api(path, creds, params)
        rows += page.get("data", [])
        if cap and len(rows) >= cap:
            return rows[:cap]
        if not page.get("has_more") or not page.get("last_id"):
            return rows
        after = page["last_id"]


def date_window(days: int, end: date | None = None) -> dict:
    """``time_ranges[]`` value for the last N days, inclusive, account timezone."""
    end = end or date.today()
    return {"type": "date_range",
            "since": (end - timedelta(days=days - 1)).isoformat(),
            "until": end.isoformat()}


def insights(creds: dict[str, str], scope: str = "ad_account", scope_id: str | None = None,
             days: int = 30, aggregation_level: str = "campaign",
             granularity: str = "daily", fields: list | None = None,
             segments: str | None = None) -> list:
    """Insights for a scope. scope in {ad_account, campaigns, ad_groups, ads}.

    Omitting ``fields`` returns only impressions + a name column, so this
    always projects the full metric set plus the row identity."""
    path = "ad_account/insights" if scope == "ad_account" else f"{scope}/{scope_id}/insights"

    if fields is None:
        fields = [f"{aggregation_level}.id", f"{aggregation_level}.name"] + \
                 [f"{aggregation_level}.{m}" for m in INSIGHT_METRICS]
        if granularity != "none":
            fields = ["metadata.readable_time"] + fields

    params: dict[str, Any] = {
        "time_granularity": granularity,
        "aggregation_level": aggregation_level,
        "fields[]": fields,
        "time_ranges[]": [date_window(days)],
    }
    if segments:
        params["segments[]"] = [segments]
    return get_all(path, creds, params)


def pixel_amount(v: Any) -> float:
    """Pixel ``amount`` is an integer in MINOR units (1499 = $14.99) while
    insights ``spend`` is a decimal in major units — the 100× trap."""
    try:
        return float(v or 0) / 100.0
    except (TypeError, ValueError):
        return 0.0
