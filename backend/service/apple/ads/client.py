"""Apple Ads (Apple Search Ads) Campaign Management API v5 — auth + transport.

Ported from the Gads project's ``asa_common.py``; the curl-subprocess transport
(a Gads sandbox-proxy workaround) is replaced with httpx, and openssl JWT
signing with pyjwt (ES256 — pyjwt converts DER→raw JOSE signatures itself).

Auth model (no browser consent flow exists — this is Apple's official method):
  user-generated EC P-256 private key → ES256 JWT "client secret" →
  client_credentials grant at appleid.apple.com → 1-hour bearer token →
  api.searchads.apple.com with an X-AP-Context: orgId=… header.

There is no refresh token; the client secret is minted on demand from the
stored private key. Access tokens are cached in-process per (client_id,
key_id) until 60s before expiry — never on disk (multi-tenant server).

v5 sunsets 2027-01-26 in favour of the Apple Ads Platform API; the version-
specific pieces (API_BASE, report envelope, orderBy defaults) live here so the
migration stays contained.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx
from utils.dates import last_n_days

API_BASE = "https://api.searchads.apple.com/api/v5"
TOKEN_URL = "https://appleid.apple.com/auth/oauth2/token"
AUDIENCE = "https://appleid.apple.com"
SCOPE = "searchadsorg"

# Report granularity → the window Apple will actually serve. Exceeding these
# returns a 400 that names the field but not the limit, so check here first.
GRANULARITY_LIMITS = {
    "HOURLY":  "startTime/endTime ≤ 7 days apart, startTime ≤ 30 days ago",
    "DAILY":   "startTime/endTime ≤ 90 days apart, startTime ≤ 90 days ago",
    "WEEKLY":  "startTime/endTime > 14 and ≤ 365 days apart, startTime ≤ 24 months ago",
    "MONTHLY": "startTime/endTime > 3 months apart, startTime ≤ 24 months ago",
}

# `selector.orderBy` is documented as optional but is REJECTED as missing on
# every reporting endpoint (REQUIRED_INPUT_ORDER_BY_MISSING). Probed against a
# live account: the id field works at every level except searchterms.
DEFAULT_ORDER_BY = {
    "campaigns": "campaignId",
    "adgroups": "adGroupId",
    "keywords": "keywordId",
    "searchterms": "impressions",
    "ads": "adId",
}


class ApiError(Exception):
    """Apple Ads error with the envelope already unpacked.

    Apple returns {"data":null,"pagination":null,"error":{"errors":[{...}]}}
    where each entry has messageCode / message / field; the OAuth endpoint uses
    a different shape ({"error":"invalid_client"}). Both are parsed.
    """

    def __init__(self, code: int, body: str):
        self.code = code
        self.body = body
        self.errors = self._parse(body)
        self.summary = "; ".join(
            " ".join(p for p in (c, f and f"[{f}]", m) if p) for c, m, f in self.errors
        ) or (body or "")[:300]
        super().__init__(f"HTTP {code} — {self.summary}")

    @staticmethod
    def _parse(body: str):
        out = []
        try:
            err = json.loads(body)
            for e in (err.get("error") or {}).get("errors", []) or []:
                out.append((e.get("messageCode", "ERROR"), e.get("message", ""), e.get("field", "")))
            if not out and isinstance(err.get("error"), str):
                out.append((err["error"], err.get("error_description", ""), ""))
        except (ValueError, AttributeError):
            pass
        return out


def require_credentials(creds: dict[str, str]) -> dict[str, str]:
    """Validate the manual-form credential shape; raise ValueError with the
    exact missing pieces rather than 401-ing halfway through a pull."""
    missing = [k for k in ("client_id", "team_id", "key_id", "private_key") if not (creds.get(k) or "").strip()]
    if missing:
        raise ValueError(
            "Apple Ads credentials incomplete — missing: " + ", ".join(missing)
            + ". Generate an EC P-256 key pair, upload the public half at "
            "ads.apple.com → Account Settings → API, then paste clientId / teamId / "
            "keyId and the private key PEM."
        )
    key = creds["private_key"].strip()
    if "BEGIN" not in key:
        raise ValueError("private_key must be the PEM text of the EC private key (-----BEGIN PRIVATE KEY-----…)")
    return creds


def client_secret(creds: dict[str, str], ttl: int = 3600) -> str:
    """Mint the ES256 client-secret JWT from the stored private key.

    Apple allows exp up to 180 days out; we mint a short-lived one per token
    request instead, so leaked non-key fields are worthless without the key.
    """
    import jwt as pyjwt

    now = int(time.time())
    return pyjwt.encode(
        {
            "sub": creds["client_id"],
            "aud": AUDIENCE,
            "iat": now - 60,  # tolerate clock skew
            "exp": now + ttl,
            "iss": creds["team_id"],
        },
        creds["private_key"],
        algorithm="ES256",
        headers={"kid": creds["key_id"]},
    )


# In-process token cache — Apple tokens live 3600s and there is no refresh flow.
_TOKEN_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_TOKEN_LOCK = threading.Lock()


def access_token(creds: dict[str, str], force: bool = False) -> str:
    require_credentials(creds)
    cache_key = (creds["client_id"], creds["key_id"])
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if not force and cached and cached["expires_at"] > time.time() + 60:
            return cached["access_token"]

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": client_secret(creds),
            "scope": SCOPE,
        },
        headers={"Host": "appleid.apple.com"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise ApiError(resp.status_code, resp.text)
    tok = resp.json()
    with _TOKEN_LOCK:
        _TOKEN_CACHE[cache_key] = {
            "access_token": tok["access_token"],
            "expires_at": time.time() + int(tok.get("expires_in", 3600)),
        }
    return tok["access_token"]


def api(
    path: str,
    creds: dict[str, str],
    method: str = "GET",
    payload: dict | None = None,
    params: dict | None = None,
    token: str | None = None,
    retries: int = 5,
    _retried_auth: bool = False,
) -> dict:
    """One Apple Ads API call. Returns the parsed body (envelope included).

    Backoff follows Apple's documented policy: 2s, 4s, 8s, 16s, then hold at 16s.
    /acls is the org-discovery call — the one endpoint that must NOT carry an
    orgId header, since you call it precisely to find out what your orgId is.
    """
    token = token or access_token(creds)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    org = (creds.get("org_id") or "").strip()
    if org and not path.lstrip("/").startswith("acls"):
        headers["X-AP-Context"] = f"orgId={org}"
    url = f"{API_BASE}/{path.lstrip('/')}"

    for attempt in range(retries):
        try:
            resp = httpx.request(
                method, url, params=params, json=payload, headers=headers, timeout=180
            )
        except httpx.HTTPError as exc:
            if attempt == retries - 1:
                raise ApiError(0, f"request failed: {exc}") from exc
            time.sleep(min(16, 2 ** (attempt + 1)))
            continue
        if resp.status_code in (200, 201):
            return resp.json() if resp.text.strip() else {}
        if resp.status_code == 204:
            return {}
        if resp.status_code == 401 and not _retried_auth:
            # cached token expired early (or the org was re-scoped) — mint once more
            return api(path, creds, method, payload, params,
                       access_token(creds, force=True), retries, True)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            time.sleep(min(16, 2 ** (attempt + 1)))
            continue
        raise ApiError(resp.status_code, resp.text)
    raise ApiError(0, "retries exhausted")


def get_all(path: str, creds: dict[str, str], limit: int = 1000, params: dict | None = None) -> list:
    """GET a collection endpoint, following offset pagination to the end."""
    token = access_token(creds)
    rows: list = []
    offset = 0
    while True:
        q = dict(params or {}, limit=limit, offset=offset)
        resp = api(path, creds, params=q, token=token)
        batch = resp.get("data") or []
        rows.extend(batch)
        total = (resp.get("pagination") or {}).get("totalResults")
        offset += len(batch)
        if not batch or (total is not None and offset >= total) or len(batch) < limit:
            return rows


def find(
    path: str,
    creds: dict[str, str],
    conditions: list | None = None,
    fields: list | None = None,
    order_by: list | None = None,
    limit: int = 1000,
) -> list:
    """POST a /find endpoint with a Selector, following pagination.

    Asymmetry with get_all(): Find endpoints carry pagination *inside* the
    selector body, not as query params.
    """
    token = access_token(creds)
    rows: list = []
    offset = 0
    while True:
        selector: dict[str, Any] = {"pagination": {"offset": offset, "limit": limit}}
        if conditions:
            selector["conditions"] = conditions
        if fields:
            selector["fields"] = fields
        if order_by:
            selector["orderBy"] = order_by
        resp = api(path, creds, method="POST", payload=selector, token=token)
        batch = resp.get("data") or []
        rows.extend(batch)
        total = (resp.get("pagination") or {}).get("totalResults")
        offset += len(batch)
        if not batch or (total is not None and offset >= total) or len(batch) < limit:
            return rows


def report_body(
    start: str,
    end: str,
    *,
    level: str,
    granularity: str | None = None,
    group_by: list | None = None,
    conditions: list | None = None,
    order_by: list | None = None,
    time_zone: str = "ORTZ",
    no_metrics: bool = False,
    row_totals: bool | None = None,
    offset: int = 0,
    limit: int = 1000,
) -> dict:
    """Build one /reports/... request body, enforcing the rules Apple only
    documents in prose: with `granularity`, returnRowTotals AND
    returnGrandTotals MUST be false; without one, returnRowTotals MUST be true.
    Getting this wrong is a 400 whose message never mentions granularity.
    `row_totals` overrides the default — age/gender/geo group_by requires both
    totals flags false."""
    if granularity and granularity not in GRANULARITY_LIMITS:
        raise ValueError(f"granularity must be one of {sorted(GRANULARITY_LIMITS)}")
    if not order_by:
        field = DEFAULT_ORDER_BY.get(level)
        if not field:
            raise ValueError(f"no default orderBy for report level {level!r} — pass order_by")
        order_by = [{"field": field, "sortOrder": "DESCENDING"}]
    selector: dict[str, Any] = {"pagination": {"offset": offset, "limit": limit}, "orderBy": order_by}
    if conditions:
        selector["conditions"] = conditions
    body: dict[str, Any] = {
        "startTime": start,
        "endTime": end,
        "timeZone": time_zone,
        "selector": selector,
        "returnRecordsWithNoMetrics": bool(no_metrics),
        "returnRowTotals": (not granularity) if row_totals is None else bool(row_totals),
        "returnGrandTotals": False,
    }
    if granularity:
        body["granularity"] = granularity
    if group_by:
        body["groupBy"] = group_by
    return body


def report(path: str, creds: dict[str, str], start: str, end: str, limit: int = 1000, **kw) -> list:
    """POST a /reports/... endpoint and return the flat list of rows."""
    level = path.rstrip("/").rsplit("/", 1)[-1]
    token = access_token(creds)
    rows: list = []
    offset = 0
    while True:
        body = report_body(start, end, level=level, offset=offset, limit=limit, **kw)
        resp = api(path, creds, method="POST", payload=body, token=token)
        batch = ((resp.get("data") or {}).get("reportingDataResponse") or {}).get("row") or []
        rows.extend(batch)
        total = (resp.get("pagination") or {}).get("totalResults")
        offset += len(batch)
        if not batch or (total is not None and offset >= total) or len(batch) < limit:
            return rows


# ------------------------------------------------------------------- helpers

def money(m: Any) -> float:
    """Apple returns Money as {"amount":"12.34","currency":"USD"} — STRINGS."""
    if not m:
        return 0.0
    try:
        return float(m.get("amount", 0) or 0)
    except (AttributeError, ValueError):
        return 0.0


# (start, end) ISO dates for the last N complete days — the shared helper
# already ends on yesterday, which is what every ad platform settles on.
date_window = last_n_days


def orgs(creds: dict[str, str]) -> list[dict]:
    """GET /acls — every org (campaign group) this API user can reach."""
    resp = api("acls", creds)
    data = resp.get("data")
    return data if isinstance(data, list) else [data] if data else []
