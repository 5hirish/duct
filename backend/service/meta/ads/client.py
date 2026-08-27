"""Meta (Facebook/Instagram) Marketing API v26.0 — auth + transport.

Ported from Gads ``meta_common.py`` (curl transport → httpx).

Auth: a long-lived **System User** token pasted by the user — no OAuth. Meta's
OAuth path needs permission App Review (screen recording), Business
Verification, and a Marketing-API access tier earned with 500 calls/15 days —
the Google-Ads-dev-token gauntlet squared. A *User* token dies in ~60 days and
takes scheduled pulls with it; a System User token (Business settings → Users
→ System users) does not expire.

Two conventions bite every first integration and are handled here:
- budgets/bids are strings in MINOR units (cents) while ``spend`` is a string
  in MAJOR units (dollars). Same response, two scales — money() vs minor().
- conversions are not columns: they arrive as an ``actions`` list of
  {action_type, value} pairs, and the SAME purchase can appear under three
  action_types. purchases() picks ONE — summing double-counts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from service.rest import Endpoint, RetryPolicy
from service.rest import ApiError as BaseApiError
from utils.dates import last_n_days

API_VERSION = "v26.0"  # released 2026-07-29; v24.0 expires 2026-10-06
API_BASE = f"https://graph.facebook.com/{API_VERSION}"

# Meta's default attribution is 7-day click + 1-day view. Google/Apple report
# last-click. Always request explicit windows so the Meta number is one you
# chose; 1d_click is the closest honest analogue to the others.
ATTRIBUTION_WINDOWS = ["1d_click", "7d_click", "1d_view"]

# The same purchase surfaces under several action_types depending on how it
# was tracked. Summing the list double-counts; prefer these, in order.
PURCHASE_ACTION_TYPES = [
    "offsite_conversion.fb_pixel_purchase",  # web pixel / CAPI
    "purchase",                              # aggregate (may duplicate the above)
    "omni_purchase",                         # cross-device rollup
    "app_custom_event.fb_mobile_purchase",   # in-app
]

# Insight fields worth pulling at every level. Deliberately excludes `reach`
# and `frequency`, which Meta refuses on some breakdowns and then fails the
# WHOLE request rather than dropping the field.
INSIGHT_FIELDS = [
    "date_start", "date_stop", "account_currency",
    "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
    "objective", "optimization_goal", "buying_type",
    "impressions", "clicks", "inline_link_clicks", "spend",
    "ctr", "inline_link_click_ctr", "cpc", "cpm",
    "actions", "action_values", "cost_per_action_type",
    "purchase_roas", "website_purchase_roas",
]

STRUCTURE_FIELDS = {
    "campaigns": ["id", "name", "status", "effective_status", "objective",
                  "buying_type", "bid_strategy", "daily_budget", "lifetime_budget",
                  "budget_remaining", "spend_cap", "start_time", "stop_time",
                  "special_ad_categories", "created_time", "updated_time"],
    "adsets": ["id", "name", "campaign_id", "status", "effective_status",
               "daily_budget", "lifetime_budget", "billing_event",
               "optimization_goal", "bid_amount", "bid_strategy",
               "promoted_object", "attribution_spec", "start_time", "end_time"],
    "ads": ["id", "name", "adset_id", "campaign_id", "status", "effective_status",
            "created_time"],
}


class ApiError(BaseApiError):
    """Graph API error with the envelope unpacked.

    The HTTP status is nearly always 400 regardless of cause, so ``api_code``
    and ``subcode`` — not the status — are what you branch on.
    """

    def parse(self, body: str) -> str:
        self.api_code: int | None = None
        self.subcode: int | None = None
        self.type = ""
        msg = ""
        try:
            err = (json.loads(body) or {}).get("error") or {}
            self.api_code = err.get("code")
            self.subcode = err.get("error_subcode")
            self.type = err.get("type") or ""
            msg = err.get("error_user_msg") or err.get("message") or ""
        except (ValueError, AttributeError):
            pass
        if not msg:
            return ""
        head = f"{self.type or 'Error'} {self.api_code if self.api_code is not None else self.status}"
        if self.subcode:
            head += f"/{self.subcode}"
        return f"{head}: {msg}"

    @property
    def is_throttle(self) -> bool:
        # 4 app-level, 17 user-level, 32 page-level, 613 custom, 80000-80004 BUC.
        return self.api_code in (4, 17, 32, 613) or (self.api_code in range(80000, 80005))

    @property
    def too_much_data(self) -> bool:
        """The sync-insights "please reduce the amount of data" bounce → retry async."""
        return self.api_code in (1, 100) and (
            "reduce the amount of data" in (self.body or "").lower()
            or "please reduce" in (self.body or "").lower()
        )

    def hint(self) -> str:
        if self.api_code == 190:
            return ("Token invalid or expired. A *User* token dies at ~60 days — "
                    "replace it with a System User token, which does not expire.")
        if self.api_code == 200 or (self.type == "OAuthException" and self.subcode == 1349125):
            return ("Token lacks a permission. The pull needs `ads_read`; assign the "
                    "System User to the ad account with at least Analyst access.")
        if self.api_code == 100 and self.subcode == 33:
            return ("Object not found *or* not visible to this token — for ad accounts "
                    "these are indistinguishable. Check the account id and that the "
                    "System User is assigned to that account.")
        if self.is_throttle:
            return "Rate limited. Meta's ad-account budget is shared across every tool touching it."
        return ""


def require_credentials(creds: dict[str, str]) -> dict[str, str]:
    if not (creds.get("access_token") or "").strip():
        raise ValueError(
            "Meta credentials incomplete — access_token missing. Create a System "
            "User token (does NOT expire): business.facebook.com → Business "
            "settings → Users → System users → Generate token with scope ads_read "
            "(+ business_management for account discovery)."
        )
    return creds


def normalize_account_id(raw: str) -> str:
    """Normalise to the `act_<digits>` form the API wants."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    return raw if raw.startswith("act_") else "act_" + raw


def _appsecret_proof(creds: dict[str, str]) -> str | None:
    """Required when the app has "Require App Secret" on; harmless otherwise."""
    secret = (creds.get("app_secret") or "").strip()
    token = (creds.get("access_token") or "").strip()
    if not (secret and token):
        return None
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def _encode(params: dict | None) -> dict | None:
    """Graph API takes structured params as JSON *strings* inside the query."""
    return {
        k: (json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else v)
        for k, v in (params or {}).items()
    } or None


class _Retry(RetryPolicy):
    """Throttles want minutes, not seconds — Meta's budgets refill on a sliding
    hour, and the HTTP status is 400 for nearly everything, so the decision has
    to come off ``api_code``."""

    def delay(self, error: ApiError, attempt: int) -> float | None:
        if attempt >= self.attempts - 1:
            return None
        if error.is_throttle:
            return min(120.0, 20.0 * (attempt + 1))
        return super().delay(error, attempt)


_ENDPOINT = Endpoint(
    base_url=API_BASE,
    error_cls=ApiError,
    retry=_Retry(attempts=5, statuses={500, 502, 503, 504}),
    timeout=300,
    success=frozenset({200, 201}),
    encode=_encode,
)


def api(path: str, creds: dict[str, str], params: dict | None = None, method: str = "GET") -> dict:
    """One Graph API call. The token rides in the Authorization header, never
    the query string (no shell history / proxy-log leaks)."""
    require_credentials(creds)
    query = dict(params or {})
    proof = _appsecret_proof(creds)
    if proof:
        query.setdefault("appsecret_proof", proof)
    return _ENDPOINT.request(
        path,
        method=method,
        params=query,
        headers={"Authorization": f"Bearer {creds['access_token']}", "Accept": "application/json"},
    )


def get_all(path: str, creds: dict[str, str], params: dict | None = None, limit: int = 200, cap: int | None = None) -> list:
    """GET an edge, following cursor pagination via `paging.next` to the end."""
    rows: list = []
    nxt: str | None = None
    while True:
        resp = api(nxt, creds) if nxt else api(path, creds, params=dict(params or {}, limit=limit))
        rows.extend(resp.get("data") or [])
        if cap and len(rows) >= cap:
            return rows[:cap]
        nxt = (resp.get("paging") or {}).get("next")
        if not nxt:
            return rows


def insights(
    obj: str,
    creds: dict[str, str],
    level: str = "campaign",
    start: str | None = None,
    end: str | None = None,
    fields: list | None = None,
    time_increment: int | None = None,
    breakdowns: list | None = None,
    filtering: list | None = None,
    limit: int = 200,
    attribution: bool = True,
) -> list:
    """GET /<obj>/insights, falling back to the async job flow when Meta balks.

    Meta answers a too-large sync request with "Please reduce the amount of
    data" (code 1/100) instead of paginating it; this catches that and re-runs
    the identical query as an async report job.
    """
    params: dict[str, Any] = {"level": level, "fields": ",".join(fields or INSIGHT_FIELDS)}
    if start and end:
        params["time_range"] = {"since": start, "until": end}
    if time_increment:
        params["time_increment"] = time_increment
    if breakdowns:
        params["breakdowns"] = ",".join(breakdowns)
    if filtering:
        params["filtering"] = filtering
    if attribution:
        params["action_attribution_windows"] = ATTRIBUTION_WINDOWS
    try:
        return get_all(f"{obj}/insights", creds, params=params, limit=limit)
    except ApiError as exc:
        if not exc.too_much_data:
            raise
        return insights_async(obj, params, creds, limit=limit)


def insights_async(obj: str, params: dict, creds: dict[str, str], limit: int = 200, poll: int = 5, timeout: int = 900) -> list:
    """POST the same insights query as a report job, poll it, read the rows."""
    job = api(f"{obj}/insights", creds, params=params, method="POST")
    run_id = job.get("report_run_id")
    if not run_id:
        raise ApiError(0, f"async insights returned no report_run_id: {job}")
    waited = 0
    while waited < timeout:
        st = api(str(run_id), creds, params={"fields": "async_status,async_percent_completion"})
        status = st.get("async_status") or ""
        if status == "Job Completed":
            return get_all(f"{run_id}/insights", creds, limit=limit)
        if status in ("Job Failed", "Job Skipped"):
            raise ApiError(0, f"async insights job {run_id} ended as {status}")
        time.sleep(poll)
        waited += poll
    raise ApiError(0, f"async insights job {run_id} still running after {timeout}s")


# ------------------------------------------------------------------- helpers

def money(v: Any) -> float:
    """`spend`, `cpc`, `cpm`, action values — strings in MAJOR units (dollars)."""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def minor(v: Any) -> float:
    """`daily_budget`, `lifetime_budget`, `bid_amount`, `spend_cap` — strings in
    MINOR units (cents). Reading these as dollars overstates budgets 100x — the
    single most common Meta reporting bug."""
    try:
        return float(v or 0) / 100.0
    except (TypeError, ValueError):
        return 0.0


def actions_map(row: dict, key: str = "actions") -> dict[str, float]:
    """Flatten the `actions` / `action_values` list into {action_type: value}."""
    out: dict[str, float] = {}
    for a in row.get(key) or []:
        try:
            out[a.get("action_type", "?")] = float(a.get("value") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def purchases(row: dict) -> tuple[float, float]:
    """(count, value) picking ONE purchase action_type — never summing.

    Summing PURCHASE_ACTION_TYPES double- or triple-counts the same order,
    which is how Meta ROAS ends up looking 3x better than Stripe's."""
    acts, vals = actions_map(row), actions_map(row, "action_values")
    for t in PURCHASE_ACTION_TYPES:
        if t in acts:
            return acts[t], vals.get(t, 0.0)
    return 0.0, 0.0


# (start, end) ISO dates for the last N complete days — the shared helper
# already ends on yesterday, which is what every ad platform settles on.
date_window = last_n_days


def adaccounts(creds: dict[str, str]) -> list[dict]:
    """GET /me/adaccounts — every ad account this token can reach."""
    return get_all("me/adaccounts", creds, params={
        "fields": "id,account_id,name,currency,timezone_name,account_status,"
                  "amount_spent,business{id,name}"
    })
