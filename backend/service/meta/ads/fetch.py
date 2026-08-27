"""Meta Marketing API read pulls + connector registration.

Ported from Gads ``fetch_meta_ads.py``. Per-section isolation: a failure is
recorded in ``errors`` and the pull continues.

Gotchas encoded (agent-facing set in agents/knowledge/meta.md):
- Without an explicit effective_status list Meta returns only ACTIVE
  campaigns and silently hides the paused history you want to audit.
- Optional ``campaign_filter`` substrings scope a shared ad account to one
  product — the filter is pushed server-side into insights `filtering` so
  other products can never contaminate aggregate rows.
- purchases() picks ONE action_type (never sums); attribution windows are
  requested explicitly (Meta default 7d-click/1d-view vs Google last-click).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)
from service.meta.ads import client as meta

logger = logging.getLogger(__name__)

_ALL_STATUSES = ["ACTIVE", "PAUSED", "CAMPAIGN_PAUSED", "ARCHIVED", "IN_PROCESS", "WITH_ISSUES"]
_ADSET_STATUSES = ["ACTIVE", "PAUSED", "ADSET_PAUSED", "CAMPAIGN_PAUSED", "ARCHIVED", "WITH_ISSUES"]


def _pull(out: dict, errors: dict, key: str, fn) -> list:
    try:
        rows = fn()
        out[key] = rows
        return rows
    except meta.ApiError as exc:
        errors[key] = exc.summary
        hint = exc.hint()
        if hint:
            errors[key] += f" → {hint}"
        logger.warning("meta_ads pull section %s failed: %s", key, exc.summary)
        # Token rejected — every other section would fail identically.
        if exc.api_code == 190:
            raise
        return []
    except Exception as exc:  # noqa: BLE001 — never abort a long pull on one section
        errors[key] = str(exc)[:500]
        logger.warning("meta_ads pull section %s failed", key, exc_info=True)
        return []


def _matches(name: str, needles: list[str]) -> bool:
    n = (name or "").lower()
    return any(x in n for x in needles)


def fetch_meta_ads(
    creds: dict[str, str],
    days: int = 30,
    campaign_filter: list[str] | None = None,
) -> dict[str, Any]:
    """Structure + insights pull for one ad account.

    ``creds``: access_token (System User), account_id, optional app_secret.
    ``campaign_filter``: case-insensitive name substrings scoping a shared
    account to one product; None = all campaigns.
    """
    meta.require_credentials(creds)
    acct = meta.normalize_account_id(creds.get("account_id") or "")
    if not acct:
        raise ValueError("Meta account_id missing — pick an ad account on the Connections page.")

    start, end = meta.date_window(days)
    prior_end = date.fromisoformat(start) - timedelta(days=1)
    prior_start = (prior_end - timedelta(days=days - 1)).isoformat()
    prior_end = prior_end.isoformat()
    needles = [s.strip().lower() for s in (campaign_filter or []) if s.strip()]

    out: dict[str, Any] = {}
    errors: dict[str, str] = {}

    _pull(out, errors, "account", lambda: [meta.api(acct, creds, params={
        "fields": "id,name,account_status,currency,timezone_name,amount_spent,"
                  "balance,spend_cap,disable_reason,business{id,name}"})])

    campaigns = _pull(out, errors, "campaigns", lambda: meta.get_all(
        f"{acct}/campaigns", creds,
        params={"fields": ",".join(meta.STRUCTURE_FIELDS["campaigns"]),
                "effective_status": _ALL_STATUSES}))

    targets = [c for c in campaigns if _matches(c.get("name"), needles)] if needles else campaigns
    ids = [c["id"] for c in targets]
    out["target_campaign_ids"] = ids
    out["name_filter"] = needles or None

    # Account-wide fetch then in-memory filter — cheaper than N per-campaign
    # edges, and keeps the campaign_id linkage Meta returns on every row.
    adsets = _pull(out, errors, "ad_sets", lambda: meta.get_all(
        f"{acct}/adsets", creds,
        params={"fields": ",".join(meta.STRUCTURE_FIELDS["adsets"]),
                "effective_status": _ADSET_STATUSES}))
    ads = _pull(out, errors, "ads", lambda: meta.get_all(
        f"{acct}/ads", creds,
        params={"fields": ",".join(meta.STRUCTURE_FIELDS["ads"]),
                "effective_status": _ADSET_STATUSES}))
    if needles and ids:
        idset = set(ids)
        out["ad_sets"] = [a for a in adsets if a.get("campaign_id") in idset]
        out["ads"] = [a for a in ads if a.get("campaign_id") in idset]

    # Pixels + custom conversions: the measurement half. An empty pixel list or
    # a stale last_fired_time explains a "no results" campaign faster than any
    # performance table.
    _pull(out, errors, "pixels", lambda: meta.get_all(
        f"{acct}/adspixels", creds,
        params={"fields": "id,name,last_fired_time,is_unavailable,"
                          "data_use_setting,enable_automatic_matching"}))
    _pull(out, errors, "custom_conversions", lambda: meta.get_all(
        f"{acct}/customconversions", creds,
        params={"fields": "id,name,custom_event_type,default_conversion_value,"
                          "last_fired_time,is_archived"}))

    if ids or not needles:
        # Push the product scoping server-side so aggregates can't be contaminated.
        filt = [{"field": "campaign.id", "operator": "IN", "value": ids}] if needles else None
        _pull(out, errors, "insights_campaigns",
              lambda: meta.insights(acct, creds, level="campaign", start=start, end=end, filtering=filt))
        _pull(out, errors, "insights_campaigns_prior",
              lambda: meta.insights(acct, creds, level="campaign", start=prior_start, end=prior_end, filtering=filt))
        _pull(out, errors, "insights_daily",
              lambda: meta.insights(acct, creds, level="campaign", start=start, end=end,
                                    time_increment=1, filtering=filt))

    # Summary with the dedup + unit rules applied.
    summary: dict[str, Any] = {}
    rows = out.get("insights_campaigns") or []
    if rows:
        spend = sum(meta.money(r.get("spend")) for r in rows)
        purchase_count = purchase_value = 0.0
        for r in rows:
            c, v = meta.purchases(r)
            purchase_count += c
            purchase_value += v
        summary = {
            "spend": round(spend, 2),
            "impressions": sum(int(r.get("impressions") or 0) for r in rows),
            "clicks": sum(int(r.get("clicks") or 0) for r in rows),
            "purchases": purchase_count,
            "purchase_value": round(purchase_value, 2),
            "roas": round(purchase_value / spend, 2) if spend else 0.0,
            "currency": rows[0].get("account_currency") or "USD",
            "note": (
                "Purchases use ONE action_type (never summed — the same order "
                "appears under up to 3 types). Meta attribution is 7d-click/"
                "1d-view vs Google/Apple last-click: never compare raw counts."
            ),
        }

    return {
        "api": f"meta-marketing-{meta.API_VERSION}",
        "account_id": acct,
        "window": [start, end],
        "prior_window": [prior_start, prior_end],
        "days": days,
        "attribution_windows": meta.ATTRIBUTION_WINDOWS,
        "summary": summary,
        "data": out,
        "errors": errors,
    }


class MetaAdsConnector:
    """Manual-credentials connector: System User token (Meta OAuth needs App
    Review + Business Verification + an earned access tier — skipped)."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        meta.require_credentials(creds)  # ValueError → 422 upstream
        try:
            rows = meta.adaccounts(creds)
        except meta.ApiError as exc:
            # Token without business_management can't discover accounts, but a
            # directly-assigned account can still be probed when given.
            acct = meta.normalize_account_id(creds.get("account_id") or "")
            if acct:
                try:
                    one = meta.api(acct, creds, params={
                        "fields": "id,account_id,name,currency,timezone_name,account_status"})
                    rows = [one]
                except meta.ApiError as exc2:
                    raise ValueError(f"Meta rejected the token: {exc2.summary}. {exc2.hint()}") from exc2
            else:
                raise ValueError(
                    f"Could not list ad accounts: {exc.summary}. {exc.hint() or ''} "
                    "Grant business_management, or paste the account id (act_…) directly."
                ) from exc
        return [
            {
                "account_id": a.get("id") or meta.normalize_account_id(str(a.get("account_id") or "")),
                "account_name": a.get("name", ""),
                "currency": a.get("currency", ""),
                "timezone": a.get("timezone_name", ""),
                "status": a.get("account_status", ""),
                "business": (a.get("business") or {}).get("name", ""),
            }
            for a in rows
        ]


META_ADS_META = ConnectorMeta(
    id="meta_ads",
    label="Meta Ads",
    oauth_scope=None,  # manual System User token — OAuth path needs app review
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(META_ADS_META, MetaAdsConnector())
