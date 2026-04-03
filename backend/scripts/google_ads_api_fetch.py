#!/usr/bin/env python3
"""Fetch Google Ads campaign rows via the API (same shape as demo_raw_payload)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Google Ads campaigns via API → raw JSON.")
    p.add_argument("--customer-id", required=True)
    p.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    p.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    p.add_argument("--account-name", default="")
    p.add_argument("--currency-code", default="USD")
    p.add_argument("--login-customer-id", default="", help="MCC / manager account ID")
    p.add_argument("--output", type=Path, help="Write raw JSON to this path")
    return p.parse_args()


def main() -> None:
    import os

    args = parse_args()
    token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")
    refresh_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "")
    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")

    if not all([token, client_id, client_secret, refresh_token]):
        raise SystemExit(
            "Set GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, "
            "GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN in the environment."
        )

    payload = fetch_campaigns(
        customer_id=args.customer_id,
        developer_token=token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        date_from=args.date_from,
        date_to=args.date_to,
        account_name=args.account_name,
        currency_code=args.currency_code,
        login_customer_id=args.login_customer_id or login_customer_id,
    )
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
