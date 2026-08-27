"""Stripe REST API — the only source of settled revenue. Auth + transport.

Ported from Gads ``stripe_common.py`` (curl → httpx).

Auth: a **restricted** read key (rk_live_…) pasted by the user. Stripe's OAuth
path exists only through published Stripe Apps (a review process); Stripe's
own guidance for self-hosted read integrations is restricted keys, so no
OAuth here. Create at dashboard.stripe.com/apikeys with read on
Subscriptions, Charges, Invoices, Customers, Products, Prices. A key missing
one resource 403s on just that call and looks healthy everywhere else — see
probe_permissions().

Money: every Stripe amount is an INTEGER in the smallest currency unit
(1999 = $19.99) — money() handles zero-decimal currencies. Timestamps are
unix seconds, UTC.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

API_BASE = "https://api.stripe.com/v1"

# Pin the version so a Stripe-side upgrade cannot silently reshape a field we
# parse. Monthly releases within a named train (acacia → … → dahlia) are
# non-breaking; a train change needs the changelog read before bumping.
STRIPE_VERSION = "2026-07-29.dahlia"

PAGE_LIMIT = 100  # Stripe's hard maximum per page
RETRY_STATUSES = {429, 500, 502, 503, 504}

# Subscription statuses that never took money: an abandoned or failed
# checkout, not a sale. Counting them as acquisition overstates it badly
# (one observed month: 31 never-paid vs 40 real).
NEVER_PAID = {"incomplete", "incomplete_expired"}


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        self.status, self.body = status, body
        detail = body
        try:
            err = json.loads(body).get("error", {})
            detail = f"{err.get('type')}: {err.get('message')}"
        except Exception:  # noqa: BLE001
            pass
        super().__init__(f"HTTP {status} — {detail}")


def require_credentials(creds: dict[str, str]) -> str:
    key = (creds.get("api_key") or "").strip()
    if not key:
        raise ValueError(
            "Stripe credentials incomplete — api_key missing. Create a RESTRICTED "
            "key (rk_live_…) at dashboard.stripe.com/apikeys with read access to "
            "Subscriptions, Charges, Invoices, Customers, Products and Prices."
        )
    return key


def key_warning(key: str) -> str:
    """Non-fatal: a full secret key works but violates least privilege."""
    if key.startswith("sk_"):
        return ("This is a FULL secret key. A restricted (rk_) read-only key is "
                "strongly preferred — Duct only ever reads.")
    return ""


def _flatten(params: dict | None, prefix: str = "") -> list[tuple[str, str]]:
    """Stripe wants nested filters as created[gte]=…, not JSON."""
    out: list[tuple[str, str]] = []
    for k, v in (params or {}).items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            out.extend(_flatten(v, key))
        elif isinstance(v, (list, tuple)):
            out.extend((f"{key}[]", str(i)) for i in v)
        elif v is not None:
            out.append((key, str(v)))
    return out


def api(path: str, creds: dict[str, str], params: dict | None = None, retries: int = 4) -> dict:
    """GET one Stripe endpoint. Returns parsed JSON, raises ApiError otherwise."""
    key = require_credentials(creds)
    url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {key}", "Stripe-Version": STRIPE_VERSION}

    delay = 1.0
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, params=_flatten(params), headers=headers, timeout=120)
        except httpx.HTTPError as exc:
            if attempt == retries:
                raise ApiError(0, f"request failed: {exc}") from exc
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in RETRY_STATUSES and attempt < retries:
            time.sleep(delay)
            delay *= 2
            continue
        raise ApiError(resp.status_code, resp.text)
    raise ApiError(0, "retries exhausted")


def get_all(path: str, creds: dict[str, str], params: dict | None = None, cap: int | None = None) -> list:
    """Follow `has_more` / `starting_after` to the end of a list endpoint.

    Stripe paginates by the LAST object's id — there is no offset. Lists come
    back newest-first, so `cap` truncates the oldest."""
    rows: list = []
    after: str | None = None
    while True:
        page_params = dict(params or {}, limit=PAGE_LIMIT)
        if after:
            page_params["starting_after"] = after
        resp = api(path, creds, page_params)
        data = resp.get("data")
        if data is None:
            return [resp]  # single object, not a list
        rows.extend(data)
        if cap and len(rows) >= cap:
            return rows[:cap]
        if not resp.get("has_more") or not data:
            return rows
        after = data[-1]["id"]


# ------------------------------------------------------------------- helpers

_ZERO_DECIMAL = {"bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
                 "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf"}


def money(minor: Any, currency: str = "usd") -> float:
    """Stripe amounts are minor units: 1999 → 19.99 (zero-decimal pass through)."""
    return (minor or 0) if (currency or "usd").lower() in _ZERO_DECIMAL else (minor or 0) / 100.0


def day(ts: Any) -> str | None:
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else None


def month(ts: Any) -> str | None:
    return time.strftime("%Y-%m", time.gmtime(ts)) if ts else None


def window(days: int, end: float | None = None) -> tuple[int, int]:
    """(gte, lte) unix bounds for the last N whole days, UTC."""
    end = end or time.time()
    return int(end - days * 86400), int(end)


def probe_permissions(creds: dict[str, str]) -> dict[str, str]:
    """Restricted keys fail per-resource. Report which reads this key has."""
    checks = [("customers", "customers"), ("charges", "charges"),
              ("subscriptions", "subscriptions"), ("invoices", "invoices"),
              ("products", "products"), ("prices", "prices")]
    out = {}
    for label, path in checks:
        try:
            api(path, creds, {"limit": 1})
            out[label] = "ok"
        except ApiError as exc:
            out[label] = f"HTTP {exc.status}"
    return out
