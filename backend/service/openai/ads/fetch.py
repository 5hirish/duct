"""OpenAI Ads read pull + connector registration.

Ported from Gads ``fetch_openai_ads.py``. The key is scoped to one ad
account, so there is no account picker beyond confirming which account the
key points at.
"""

from __future__ import annotations

import logging
from typing import Any

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)
from service.openai.ads import client as oai

logger = logging.getLogger(__name__)


def _pull(out: dict, errors: dict, key: str, fn) -> list:
    try:
        rows = fn()
        out[key] = rows
        return rows
    except oai.ApiError as exc:
        errors[key] = exc.detail or str(exc)
        hint = exc.hint()
        if hint:
            errors[key] += f" → {hint}"
        logger.warning("openai_ads pull section %s failed: %s", key, exc)
        if exc.code == 401:
            raise ValueError(f"OpenAI Ads rejected the key: {exc.detail}. {hint}") from exc
        return []
    except Exception as exc:  # noqa: BLE001 — never abort a long pull on one section
        errors[key] = str(exc)[:500]
        logger.warning("openai_ads pull section %s failed", key, exc_info=True)
        return []


def fetch_openai_ads(creds: dict[str, str], days: int = 30) -> dict[str, Any]:
    oai.require_credentials(creds)
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}

    _pull(out, errors, "ad_account", lambda: [oai.api("ad_account", creds)])
    _pull(out, errors, "campaigns", lambda: oai.get_all("campaigns", creds))
    rows = _pull(out, errors, "insights_campaigns",
                 lambda: oai.insights(creds, days=days, aggregation_level="campaign",
                                      granularity="none"))
    _pull(out, errors, "insights_daily",
          lambda: oai.insights(creds, days=days, aggregation_level="ad_account",
                               granularity="daily"))

    summary: dict[str, Any] = {}
    if rows:
        def metric(row: dict, name: str) -> float:
            try:
                return float(row.get(f"campaign.{name}") or 0)
            except (TypeError, ValueError):
                return 0.0

        spend = sum(metric(r, "spend") for r in rows)
        clicks = sum(metric(r, "clicks") for r in rows)
        summary = {
            "spend": round(spend, 2),
            "impressions": int(sum(metric(r, "impressions") for r in rows)),
            "clicks": int(clicks),
            "cpc": round(spend / clicks, 2) if clicks else 0.0,
            "note": (
                "OpenAI Ads insights CANNOT see conversions — the metric set is "
                "impressions/clicks/spend/ctr/cpc/cpm only. Pixel conversions "
                "exist solely in the Ads Manager UI; judge this channel against "
                "the billing source, never on CPC alone. Also: pixel amounts are "
                "integer MINOR units while insights spend is decimal major units."
            ),
        }

    return {
        "api": "openai-ads-v1",
        "days": days,
        "summary": summary,
        "data": out,
        "errors": errors,
    }


class OpenAIAdsConnector:
    """Manual API-key connector — no OAuth exists; access itself is gated beta."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        oai.require_credentials(creds)  # ValueError → 422 upstream
        try:
            acct = oai.api("ad_account", creds)
        except oai.ApiError as exc:
            if exc.code in (401, 403):
                raise ValueError(f"OpenAI Ads rejected the key: {exc.detail}. {exc.hint()}") from exc
            raise RuntimeError(f"OpenAI Ads account lookup failed: {exc}") from exc
        return [{
            "account_id": str(acct.get("id", "")),
            "account_name": acct.get("name", "") or f"Ad account {acct.get('id', '')}",
            "currency": acct.get("currency", ""),
        }]


OPENAI_ADS_META = ConnectorMeta(
    id="openai_ads",
    label="OpenAI Ads",
    oauth_scope=None,  # bearer key scoped to one ad account — no OAuth exists
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(OPENAI_ADS_META, OpenAIAdsConnector())
