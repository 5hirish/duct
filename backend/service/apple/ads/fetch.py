"""Apple Search Ads read pulls + connector registration.

Ported from Gads ``fetch_apple_ads.py``. Every section is fetched
independently — a failure is recorded in ``errors`` and the rest of the pull
continues (the per-section isolation rule).

Gotchas encoded (see agents/knowledge/apple_ads.md for the agent-facing set):
- Money fields are STRINGS ({"amount":"12.34"}) — client.money() parses them.
- ``/reports/campaigns`` is ORG-scoped: without campaign conditions it mixes
  every app in the org into the totals (tenancy contamination). The pull
  always scopes report calls to the discovered campaign ids.
- v5 renamed ``installs`` → ``tapInstalls``/``totalInstalls``.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from service.apple.ads import client as asa
from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)

logger = logging.getLogger(__name__)


def _pull(out: dict, errors: dict, key: str, fn) -> list:
    try:
        rows = fn()
        out[key] = rows
        return rows
    except Exception as exc:  # noqa: BLE001 — never abort a long pull on one section
        errors[key] = str(exc)[:500]
        logger.warning("apple_ads pull section %s failed: %s", key, exc)
        return []


def _slim_report_row(row: dict) -> dict:
    meta = row.get("metadata") or {}
    total = row.get("total") or {}
    # v5: installs → tapInstalls (tap-through) / totalInstalls (incl. view-through)
    return {
        "campaign_id": meta.get("campaignId"),
        "campaign_name": meta.get("campaignName"),
        "status": meta.get("campaignStatus") or meta.get("status"),
        "impressions": total.get("impressions", 0),
        "taps": total.get("taps", 0),
        "tap_installs": total.get("tapInstalls", total.get("installs", 0)),
        "total_installs": total.get("totalInstalls", 0),
        "spend": asa.money(total.get("localSpend")),
        "avg_cpt": asa.money(total.get("avgCPT")),
        "currency": (total.get("localSpend") or {}).get("currency"),
        "granularity": row.get("granularity") or [],
    }


def fetch_apple_ads(creds: dict[str, str], days: int = 30) -> dict[str, Any]:
    """The read pull: campaigns + org-scoped-but-campaign-conditioned reports."""
    asa.require_credentials(creds)
    start, end = asa.date_window(days)
    prior_start, prior_end = asa.date_window(days, end=date.fromisoformat(start) - timedelta(days=1))

    out: dict[str, Any] = {}
    errors: dict[str, str] = {}

    campaigns = _pull(out, errors, "campaigns", lambda: asa.get_all("campaigns", creds))
    ids = [c.get("id") for c in campaigns if c.get("id")]
    out["campaign_count"] = len(ids)

    # ORG-SCOPED reports — always condition on the campaign ids so another
    # app's spend in the same org can never contaminate these totals.
    conditions = (
        [{"field": "campaignId", "operator": "IN", "values": [str(i) for i in ids]}]
        if ids
        else None
    )
    if ids:
        _pull(out, errors, "report_campaigns", lambda: [
            _slim_report_row(r)
            for r in asa.report("reports/campaigns", creds, start, end, conditions=conditions)
        ])
        _pull(out, errors, "report_campaigns_prior", lambda: [
            _slim_report_row(r)
            for r in asa.report("reports/campaigns", creds, prior_start, prior_end, conditions=conditions)
        ])
        _pull(out, errors, "report_daily", lambda: [
            _slim_report_row(r)
            for r in asa.report(
                "reports/campaigns", creds, start, end,
                granularity="DAILY", conditions=conditions,
            )
        ])

    summary: dict[str, Any] = {}
    rows = out.get("report_campaigns") or []
    if rows:
        summary = {
            "spend": round(sum(r["spend"] for r in rows), 2),
            "impressions": sum(r["impressions"] for r in rows),
            "taps": sum(r["taps"] for r in rows),
            "tap_installs": sum(r["tap_installs"] for r in rows),
            "total_installs": sum(r["total_installs"] for r in rows),
            "note": (
                "Apple attributes installs only — no revenue or downstream "
                "conversion metric exists here. Reconcile value against the "
                "billing source (Stripe/RevenueCat), never against installs."
            ),
        }

    return {
        "api": "apple-search-ads-v5",
        "window": [start, end],
        "prior_window": [prior_start, prior_end],
        "days": days,
        "summary": summary,
        "data": out,
        "errors": errors,
    }


class AppleAdsConnector:
    """Manual-credentials connector: EC key material, no browser consent."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        try:
            asa.require_credentials(creds)
        except ValueError:
            raise
        try:
            rows = asa.orgs(creds)
        except asa.ApiError as exc:
            if exc.code in (400, 401, 403):
                raise ValueError(
                    f"Apple rejected the credentials: {exc.summary}. Check that the "
                    "public key is uploaded and clientId/teamId/keyId match."
                ) from exc
            raise RuntimeError(f"Apple Ads org listing failed: {exc}") from exc
        return [
            {
                "account_id": str(org.get("orgId", "")),
                "account_name": org.get("orgName", "") or f"Org {org.get('orgId')}",
                "currency": org.get("currency", ""),
                "payment_model": org.get("paymentModel", ""),
                "role_names": org.get("roleNames", []),
            }
            for org in rows
        ]


APPLE_ADS_META = ConnectorMeta(
    id="apple_ads",
    label="Apple Search Ads",
    oauth_scope=None,  # manual key material — no browser OAuth exists
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(APPLE_ADS_META, AppleAdsConnector())
