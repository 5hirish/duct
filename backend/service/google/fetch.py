"""Fetch Google Ads data via the API.

Base fetch (campaign performance) is always used. Supplementary fetches
(search terms, device, geo, ad group) are goal-driven — registered as
LangChain tools so the agent picks which to call based on the user's goal.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, DefaultDict, Dict, List, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

logger = logging.getLogger(__name__)


def _norm_customer_id(customer_id: str) -> str:
    return customer_id.replace("-", "").strip()


def _parse_ymd(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _previous_window(date_from: str, date_to: str) -> Tuple[str, str]:
    d0 = _parse_ymd(date_from)
    d1 = _parse_ymd(date_to)
    days = (d1 - d0).days + 1
    prev_end = d0 - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start.isoformat(), prev_end.isoformat()


def _gaql(date_from: str, date_to: str) -> str:
    return f"""
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  metrics.clicks,
  metrics.impressions,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
  AND campaign.status != 'REMOVED'
ORDER BY campaign.id
""".strip()


def _enum_name(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value)


def _aggregate_rows(client: GoogleAdsClient, customer_id: str, date_from: str, date_to: str) -> Dict[int, Dict[str, Any]]:
    ga_service = client.get_service("GoogleAdsService")
    query = _gaql(date_from, date_to)
    cid_norm = _norm_customer_id(customer_id)

    agg: DefaultDict[int, Dict[str, Any]] = defaultdict(
        lambda: {
            "clicks": 0,
            "impressions": 0,
            "cost_micros": 0,
            "conversions": 0.0,
            "conversions_value": 0.0,
            "campaign_name": "",
            "status": "",
            "channel_type": "",
        }
    )

    try:
        stream = ga_service.search_stream(customer_id=cid_norm, query=query)
    except GoogleAdsException as exc:
        raise RuntimeError(exc.failure.errors[0].message if exc.failure.errors else str(exc)) from exc

    for batch in stream:
        for row in batch.results:
            cid = int(row.campaign.id)
            bucket = agg[cid]
            m = row.metrics
            bucket["clicks"] += m.clicks
            bucket["impressions"] += m.impressions
            bucket["cost_micros"] += m.cost_micros
            bucket["conversions"] += m.conversions
            bucket["conversions_value"] += m.conversions_value
            if not bucket["campaign_name"]:
                bucket["campaign_name"] = row.campaign.name
                bucket["status"] = _enum_name(row.campaign.status)
                bucket["channel_type"] = _enum_name(row.campaign.advertising_channel_type)

    return dict(agg)


def _bucket_to_row(cid: int, bucket: Dict[str, Any], previous: Dict[str, float]) -> Dict[str, Any]:
    clicks = int(bucket["clicks"])
    impressions = int(bucket["impressions"])
    spend = bucket["cost_micros"] / 1_000_000.0
    conversions = float(bucket["conversions"])
    conversion_value = float(bucket["conversions_value"])
    ctr = (clicks / impressions) if impressions else 0.0
    average_cpc = (spend / clicks) if clicks else 0.0
    cost_per_conversion = (spend / conversions) if conversions else 0.0
    roas = (conversion_value / spend) if spend else 0.0

    return {
        "campaign_name": bucket["campaign_name"] or f"Campaign {cid}",
        "campaign_id": str(cid),
        "channel_type": bucket["channel_type"] or None,
        "status": bucket["status"] or None,
        "clicks": clicks,
        "impressions": impressions,
        "spend": spend,
        "ctr": ctr,
        "average_cpc": average_cpc,
        "conversions": conversions,
        "cost_per_conversion": cost_per_conversion,
        "conversion_value": conversion_value,
        "roas": roas,
        "previous": previous,
    }


def _previous_slice(prev_bucket: Dict[str, Any] | None) -> Dict[str, float]:
    if not prev_bucket:
        return {
            "clicks": 0.0,
            "impressions": 0.0,
            "spend": 0.0,
            "conversions": 0.0,
            "conversion_value": 0.0,
        }
    spend = prev_bucket["cost_micros"] / 1_000_000.0
    return {
        "clicks": float(prev_bucket["clicks"]),
        "impressions": float(prev_bucket["impressions"]),
        "spend": spend,
        "conversions": float(prev_bucket["conversions"]),
        "conversion_value": float(prev_bucket["conversions_value"]),
    }


def fetch_campaigns(
    customer_id: str,
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    date_from: str,
    date_to: str,
    account_name: str = "",
    currency_code: str = "USD",
    login_customer_id: str = "",
) -> dict:
    """Return raw payload dict matching ``demo_raw_payload()`` shape."""
    prev_from, prev_to = _previous_window(date_from, date_to)

    creds: Dict[str, Any] = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    if login_customer_id and login_customer_id.strip():
        creds["login_customer_id"] = _norm_customer_id(login_customer_id)

    client = GoogleAdsClient.load_from_dict(creds)

    current = _aggregate_rows(client, customer_id, date_from, date_to)
    previous = _aggregate_rows(client, customer_id, prev_from, prev_to)

    rows: List[Dict[str, Any]] = []
    for cid, bucket in sorted(
        current.items(),
        key=lambda item: item[1]["cost_micros"],
        reverse=True,
    ):
        prev_b = previous.get(cid)
        rows.append(_bucket_to_row(cid, bucket, _previous_slice(prev_b)))

    display_id = customer_id.strip()
    meta_name = account_name.strip() or f"Google Ads {display_id}"

    return {
        "source_metadata": {
            "source": "google_ads_api",
            "export_type": "campaign_performance",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_current": f"{date_from} to {date_to}",
            "window_previous": f"{prev_from} to {prev_to}",
            "currency_code": currency_code,
            "account_name": meta_name,
            "account_id": display_id or None,
            "source_file": None,
            "notes": [
                "Live Google Ads API fetch",
                "Metrics aggregated per campaign over date range",
            ],
        },
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Supplementary GAQL fetches — goal-driven, called via agent tools
# ---------------------------------------------------------------------------

def _build_client(
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str = "",
) -> GoogleAdsClient:
    """Build a GoogleAdsClient from explicit credentials."""
    creds: Dict[str, Any] = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    if login_customer_id and login_customer_id.strip():
        creds["login_customer_id"] = _norm_customer_id(login_customer_id)
    return GoogleAdsClient.load_from_dict(creds)


def _safe_micros(micros: int) -> float:
    return micros / 1_000_000.0


def _run_query(
    client: GoogleAdsClient, customer_id: str, query: str
) -> List[Any]:
    """Execute a GAQL query and return all result rows."""
    ga_service = client.get_service("GoogleAdsService")
    cid = _norm_customer_id(customer_id)
    try:
        stream = ga_service.search_stream(customer_id=cid, query=query)
    except GoogleAdsException as exc:
        msg = exc.failure.errors[0].message if exc.failure.errors else str(exc)
        raise RuntimeError(msg) from exc
    results = []
    for batch in stream:
        results.extend(batch.results)
    return results


# -- Search terms ------------------------------------------------------

_SEARCH_TERMS_GAQL = """
SELECT
  campaign.id,
  campaign.name,
  search_term_view.search_term,
  segments.search_term_match_type,
  metrics.clicks,
  metrics.impressions,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM search_term_view
WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
ORDER BY metrics.cost_micros DESC
LIMIT 100
""".strip()


def fetch_search_terms(
    customer_id: str,
    date_from: str,
    date_to: str,
    *,
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str = "",
) -> Dict[str, Any]:
    """Fetch top search terms by spend. Useful for CAC and spend-audit goals."""
    client = _build_client(developer_token, client_id, client_secret, refresh_token, login_customer_id)
    query = _SEARCH_TERMS_GAQL.format(date_from=date_from, date_to=date_to)
    raw = _run_query(client, customer_id, query)

    rows: List[Dict[str, Any]] = []
    for r in raw:
        spend = _safe_micros(r.metrics.cost_micros)
        clicks = int(r.metrics.clicks)
        impressions = int(r.metrics.impressions)
        conversions = float(r.metrics.conversions)
        conv_value = float(r.metrics.conversions_value)
        rows.append({
            "search_term": r.search_term_view.search_term,
            "match_type": _enum_name(r.segments.search_term_match_type),
            "campaign_name": r.campaign.name,
            "campaign_id": str(r.campaign.id),
            "clicks": clicks,
            "impressions": impressions,
            "spend": spend,
            "ctr": (clicks / impressions) if impressions else 0.0,
            "conversions": conversions,
            "cost_per_conversion": (spend / conversions) if conversions else 0.0,
            "conversion_value": conv_value,
            "roas": (conv_value / spend) if spend else 0.0,
        })
    return {
        "report_type": "search_terms",
        "date_range": f"{date_from} to {date_to}",
        "row_count": len(rows),
        "rows": rows,
    }


# -- Device performance ------------------------------------------------

_DEVICE_GAQL = """
SELECT
  campaign.id,
  campaign.name,
  segments.device,
  metrics.clicks,
  metrics.impressions,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
  AND campaign.status != 'REMOVED'
""".strip()


def fetch_device_performance(
    customer_id: str,
    date_from: str,
    date_to: str,
    *,
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str = "",
) -> Dict[str, Any]:
    """Fetch campaign performance segmented by device (MOBILE, DESKTOP, TABLET)."""
    client = _build_client(developer_token, client_id, client_secret, refresh_token, login_customer_id)
    query = _DEVICE_GAQL.format(date_from=date_from, date_to=date_to)
    raw = _run_query(client, customer_id, query)

    # Aggregate by (campaign_id, device)
    agg: DefaultDict[tuple, Dict[str, Any]] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "cost_micros": 0, "conversions": 0.0, "conversions_value": 0.0,
                 "campaign_name": "", "device": ""}
    )
    for r in raw:
        key = (int(r.campaign.id), _enum_name(r.segments.device))
        bucket = agg[key]
        bucket["clicks"] += r.metrics.clicks
        bucket["impressions"] += r.metrics.impressions
        bucket["cost_micros"] += r.metrics.cost_micros
        bucket["conversions"] += r.metrics.conversions
        bucket["conversions_value"] += r.metrics.conversions_value
        if not bucket["campaign_name"]:
            bucket["campaign_name"] = r.campaign.name
            bucket["device"] = _enum_name(r.segments.device)

    rows: List[Dict[str, Any]] = []
    for (cid, device), bucket in sorted(agg.items(), key=lambda x: x[1]["cost_micros"], reverse=True):
        spend = _safe_micros(bucket["cost_micros"])
        clicks = int(bucket["clicks"])
        impressions = int(bucket["impressions"])
        conversions = float(bucket["conversions"])
        conv_value = float(bucket["conversions_value"])
        rows.append({
            "campaign_name": bucket["campaign_name"],
            "campaign_id": str(cid),
            "device": device,
            "clicks": clicks,
            "impressions": impressions,
            "spend": spend,
            "ctr": (clicks / impressions) if impressions else 0.0,
            "conversions": conversions,
            "cost_per_conversion": (spend / conversions) if conversions else 0.0,
            "conversion_value": conv_value,
            "roas": (conv_value / spend) if spend else 0.0,
        })
    return {
        "report_type": "device_performance",
        "date_range": f"{date_from} to {date_to}",
        "row_count": len(rows),
        "rows": rows,
    }


# -- Geographic performance -------------------------------------------

_GEO_GAQL = """
SELECT
  campaign.id,
  campaign.name,
  geographic_view.country_criterion_id,
  geographic_view.location_type,
  metrics.clicks,
  metrics.impressions,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM geographic_view
WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
ORDER BY metrics.cost_micros DESC
LIMIT 100
""".strip()


def fetch_geo_performance(
    customer_id: str,
    date_from: str,
    date_to: str,
    *,
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str = "",
) -> Dict[str, Any]:
    """Fetch geographic performance data. Useful for scaling and spend-audit goals."""
    client = _build_client(developer_token, client_id, client_secret, refresh_token, login_customer_id)
    query = _GEO_GAQL.format(date_from=date_from, date_to=date_to)
    raw = _run_query(client, customer_id, query)

    rows: List[Dict[str, Any]] = []
    for r in raw:
        spend = _safe_micros(r.metrics.cost_micros)
        clicks = int(r.metrics.clicks)
        impressions = int(r.metrics.impressions)
        conversions = float(r.metrics.conversions)
        conv_value = float(r.metrics.conversions_value)
        rows.append({
            "campaign_name": r.campaign.name,
            "campaign_id": str(r.campaign.id),
            "country_criterion_id": str(r.geographic_view.country_criterion_id),
            "location_type": _enum_name(r.geographic_view.location_type),
            "clicks": clicks,
            "impressions": impressions,
            "spend": spend,
            "ctr": (clicks / impressions) if impressions else 0.0,
            "conversions": conversions,
            "cost_per_conversion": (spend / conversions) if conversions else 0.0,
            "conversion_value": conv_value,
            "roas": (conv_value / spend) if spend else 0.0,
        })
    return {
        "report_type": "geo_performance",
        "date_range": f"{date_from} to {date_to}",
        "row_count": len(rows),
        "rows": rows,
    }


# -- Ad group performance ---------------------------------------------

_AD_GROUP_GAQL = """
SELECT
  campaign.id,
  campaign.name,
  ad_group.id,
  ad_group.name,
  ad_group.status,
  metrics.clicks,
  metrics.impressions,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM ad_group
WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
  AND campaign.status != 'REMOVED'
  AND ad_group.status != 'REMOVED'
ORDER BY metrics.cost_micros DESC
LIMIT 100
""".strip()


def fetch_ad_group_performance(
    customer_id: str,
    date_from: str,
    date_to: str,
    *,
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str = "",
) -> Dict[str, Any]:
    """Fetch ad group level performance. Deeper than campaign for spend audit and ROAS goals."""
    client = _build_client(developer_token, client_id, client_secret, refresh_token, login_customer_id)
    query = _AD_GROUP_GAQL.format(date_from=date_from, date_to=date_to)
    raw = _run_query(client, customer_id, query)

    # Aggregate by ad_group.id across date segments
    agg: DefaultDict[int, Dict[str, Any]] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "cost_micros": 0, "conversions": 0.0, "conversions_value": 0.0,
                 "campaign_name": "", "campaign_id": 0, "ad_group_name": "", "status": ""}
    )
    for r in raw:
        agid = int(r.ad_group.id)
        bucket = agg[agid]
        bucket["clicks"] += r.metrics.clicks
        bucket["impressions"] += r.metrics.impressions
        bucket["cost_micros"] += r.metrics.cost_micros
        bucket["conversions"] += r.metrics.conversions
        bucket["conversions_value"] += r.metrics.conversions_value
        if not bucket["ad_group_name"]:
            bucket["campaign_name"] = r.campaign.name
            bucket["campaign_id"] = int(r.campaign.id)
            bucket["ad_group_name"] = r.ad_group.name
            bucket["status"] = _enum_name(r.ad_group.status)

    rows: List[Dict[str, Any]] = []
    for agid, bucket in sorted(agg.items(), key=lambda x: x[1]["cost_micros"], reverse=True):
        spend = _safe_micros(bucket["cost_micros"])
        clicks = int(bucket["clicks"])
        impressions = int(bucket["impressions"])
        conversions = float(bucket["conversions"])
        conv_value = float(bucket["conversions_value"])
        rows.append({
            "campaign_name": bucket["campaign_name"],
            "campaign_id": str(bucket["campaign_id"]),
            "ad_group_name": bucket["ad_group_name"],
            "ad_group_id": str(agid),
            "status": bucket["status"],
            "clicks": clicks,
            "impressions": impressions,
            "spend": spend,
            "ctr": (clicks / impressions) if impressions else 0.0,
            "conversions": conversions,
            "cost_per_conversion": (spend / conversions) if conversions else 0.0,
            "conversion_value": conv_value,
            "roas": (conv_value / spend) if spend else 0.0,
        })
    return {
        "report_type": "ad_group_performance",
        "date_range": f"{date_from} to {date_to}",
        "row_count": len(rows),
        "rows": rows,
    }
