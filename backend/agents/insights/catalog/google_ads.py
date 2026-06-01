"""Entity catalog for Google Ads supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "google_ads",
    "schema_version": "1.0.0",
    "last_audited": "2026-04-28",
    "api_version": "v18",
    "audit_notes": "Verified against google-ads v30 client fields used in service/google fetchers.",
    "entities": [
        {
            "entity_id": "campaign_performance",
            "label": "Campaign Performance",
            "tool": "fetch_campaign_performance",
            "description": (
                "Per-campaign spend, clicks, impressions, conversions, conversion value, "
                "ROAS, CPA, and period comparison."
            ),
            "fields": {
                "campaign_name": {"type": "dimension", "label": "Campaign"},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "clicks": {"type": "metric", "unit": "count", "agg": "sum"},
                "impressions": {"type": "metric", "unit": "count", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "conversion_value": {"type": "metric", "unit": "currency", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cost_per_conversion": {"type": "metric", "unit": "currency", "agg": "avg"},
                "ctr": {"type": "metric", "unit": "percent", "agg": "avg"},
                "action": {
                    "type": "classification",
                    "values": ["scale", "pause", "monitor", "refine", "refresh", "investigate"],
                },
            },
            "sortable_by": ["spend", "roas", "cost_per_conversion", "conversions"],
            "typical_row_count": "5-50 campaigns",
        },
        {
            "entity_id": "search_terms",
            "label": "Search Terms",
            "tool": "fetch_search_terms",
            "description": "Top search terms by spend with match type and efficiency metrics.",
            "fields": {
                "search_term": {"type": "dimension", "label": "Search Term"},
                "campaign_name": {"type": "dimension"},
                "match_type": {"type": "dimension", "values": ["EXACT", "PHRASE", "BROAD"]},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "clicks": {"type": "metric", "unit": "count", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "cost_per_conversion": {"type": "metric", "unit": "currency", "agg": "avg"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "ctr": {"type": "metric", "unit": "percent", "agg": "avg"},
            },
            "sortable_by": ["spend", "cost_per_conversion", "roas", "conversions"],
            "typical_row_count": "up to 100 terms",
        },
        {
            "entity_id": "device_performance",
            "label": "Device Performance",
            "tool": "fetch_device_performance",
            "description": "Campaign by device segmentation with efficiency signals.",
            "fields": {
                "campaign_name": {"type": "dimension"},
                "device": {"type": "dimension", "values": ["MOBILE", "DESKTOP", "TABLET"]},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cost_per_conversion": {"type": "metric", "unit": "currency", "agg": "avg"},
            },
        },
        {
            "entity_id": "geo_performance",
            "label": "Geographic Performance",
            "tool": "fetch_geo_performance",
            "description": "Geographic breakdown by campaign with spend and conversion efficiency.",
            "fields": {
                "campaign_name": {"type": "dimension"},
                "country_criterion_id": {"type": "dimension"},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cost_per_conversion": {"type": "metric", "unit": "currency", "agg": "avg"},
            },
        },
        {
            "entity_id": "ad_group_performance",
            "label": "Ad Group Performance",
            "tool": "fetch_ad_group_performance",
            "description": "Ad group level performance for deeper optimization within campaigns.",
            "fields": {
                "campaign_name": {"type": "dimension"},
                "ad_group_name": {"type": "dimension"},
                "spend": {"type": "metric", "unit": "currency", "agg": "sum"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "roas": {"type": "metric", "unit": "ratio", "agg": "avg"},
                "cost_per_conversion": {"type": "metric", "unit": "currency", "agg": "avg"},
            },
        },
    ],
}
