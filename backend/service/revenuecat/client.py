"""RevenueCat REST API v2 — iOS/Android subscription truth. Auth + transport.

Ported from Gads ``rc_common.py`` (curl → httpx).

Auth: a v2 **secret** API key pasted by the user (Project settings → API keys
→ Secret API key V2). RevenueCat now has an OAuth server, but client
registration is manual via support email — the manual key ships first.

Key sharp edges handled here:
- The public SDK keys (appl_/goog_/amzn_/rcb_) can never read the REST API —
  rejected at validation time with the exact fix.
- v2 keys are granular and the dashboard defaults a new key to NOTHING: a key
  missing only the charts scope 403s on metrics and looks healthy elsewhere.
- Charts/metrics has a 25 req/min budget (vs 480 for customer info) —
  ``throttle=True`` self-paces instead of discovering it via 429s.
- v2 ``next_page`` is a RELATIVE path — naive joining double-prefixes /v2.
"""

from __future__ import annotations

import json
import threading
import time

import httpx

API_BASE = "https://api.revenuecat.com/v2"

RATE_LIMITS = {
    "customer_info": 480,   # req/min — /customers, /subscriptions, /purchases
    "charts_metrics": 25,   # req/min — /metrics/*, /charts/*
}
CHART_MIN_INTERVAL = 60.0 / RATE_LIMITS["charts_metrics"]  # 2.4s between chart calls

# Permissions a v2 key needs for a full read-only pull.
READ_SCOPES = [
    "project_configuration:projects:read",
    "project_configuration:apps:read",
    "project_configuration:products:read",
    "project_configuration:entitlements:read",
    "project_configuration:offerings:read",
    "customer_information:customers:read",
    "customer_information:subscriptions:read",
    "customer_information:purchases:read",
    "charts_metrics:overview:read",
]

_PUBLIC_KEY_PREFIXES = ("appl_", "goog_", "amzn_", "rcb_")


class ApiError(Exception):
    """v2 error with the envelope unpacked: {"type","param","message",
    "doc_url","retryable","backoff_ms"}."""

    def __init__(self, code: int, body: str, url: str = ""):
        self.code = code
        self.body = body
        self.url = url
        self.type = ""
        self.param = ""
        self.retryable = False
        self.backoff_ms: int | None = None
        msg = ""
        try:
            err = json.loads(body)
            if isinstance(err, dict):
                self.type = err.get("type") or ""
                self.param = err.get("param") or ""
                self.retryable = bool(err.get("retryable"))
                self.backoff_ms = err.get("backoff_ms")
                msg = err.get("message") or ""
        except (ValueError, AttributeError):
            pass
        bits = [b for b in (self.type, self.param and f"[{self.param}]", msg) if b]
        self.summary = " ".join(bits) or (body or "")[:300]
        super().__init__(f"HTTP {code} — {self.summary}")

    def hint(self) -> str:
        if self.code == 401:
            return ("Key rejected. RevenueCat v2 keys are *secret* keys from Project "
                    "settings → API keys — a public SDK key or a v1 key will never work.")
        if self.code == 403:
            return ("Key authenticated but lacks a permission. Edit the key and grant: "
                    + ", ".join(READ_SCOPES))
        if self.code == 429:
            return (f"Rate limited ({RATE_LIMITS['charts_metrics']}/min on charts & "
                    "metrics, 480/min on customer info).")
        return ""


def require_credentials(creds: dict[str, str]) -> str:
    key = (creds.get("api_key") or "").strip()
    if not key:
        raise ValueError(
            "RevenueCat credentials incomplete — api_key missing. Create a "
            "**Secret API key (V2)** at app.revenuecat.com → Project settings → "
            "API keys, granting: " + ", ".join(READ_SCOPES)
        )
    if key.startswith(_PUBLIC_KEY_PREFIXES):
        raise ValueError(
            f"That looks like a *public SDK* key ({key[:5]}…) — those are for the "
            "mobile SDK and cannot read the REST API. You need a Secret API key (V2)."
        )
    return key


_last_chart_call = [0.0]
_chart_lock = threading.Lock()


def api(path: str, creds: dict[str, str], params: dict | None = None,
        retries: int = 5, throttle: bool = False) -> dict:
    """One RevenueCat call. ``throttle=True`` self-paces to the charts budget."""
    key = require_credentials(creds)
    url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"

    if throttle:
        with _chart_lock:
            wait = CHART_MIN_INTERVAL - (time.time() - _last_chart_call[0])
            if wait > 0:
                time.sleep(wait)
            _last_chart_call[0] = time.time()

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=180)
        except httpx.HTTPError as exc:
            if attempt == retries - 1:
                raise ApiError(0, f"request failed: {exc}", url) from exc
            time.sleep(min(16, 2 ** (attempt + 1)))
            continue
        if resp.status_code == 200:
            return resp.json() if resp.text.strip() else {}
        if resp.status_code == 204:
            return {}
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            # Honour the server's own backoff hint when it sends one.
            err = ApiError(resp.status_code, resp.text, url)
            delay = (err.backoff_ms / 1000.0) if err.backoff_ms else min(30, 2 ** (attempt + 1))
            time.sleep(delay)
            continue
        raise ApiError(resp.status_code, resp.text, url)
    raise ApiError(0, "retries exhausted", url)


def get_all(path: str, creds: dict[str, str], params: dict | None = None,
            limit: int = 100, cap: int | None = None) -> list:
    """GET a v2 list endpoint, following `next_page` to the end.

    v2 list shape: {"object":"list","items":[…],"next_page":"/v2/…"} —
    ``next_page`` is a RELATIVE path (or null), NOT a full URL; joining it onto
    API_BASE naively double-prefixes /v2. Handled here."""
    rows: list = []
    page: str | None = None
    while True:
        if page:
            nxt = page if page.startswith("http") else "https://api.revenuecat.com" + (
                page if page.startswith("/") else "/" + page)
            resp = api(nxt, creds)
        else:
            resp = api(path, creds, params=dict(params or {}, limit=limit))
        items = resp.get("items")
        if items is None:  # single object, not a list endpoint
            return [resp]
        rows.extend(items)
        if cap and len(rows) >= cap:
            return rows[:cap]
        page = resp.get("next_page")
        if not page:
            return rows


def projects(creds: dict[str, str]) -> list[dict]:
    """GET /v2/projects — every project this key can reach (usually one)."""
    return get_all("projects", creds)
