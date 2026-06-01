"""Entity catalog for GA4 supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "ga4",
    "schema_version": "1.0.0",
    "last_audited": "2026-04-28",
    "api_version": "ga4-data-v1beta",
    "audit_notes": "Aligned with service/google/ga4.py response fields used by insight tools.",
    "entities": [
        {
            "entity_id": "ga4_landing_pages",
            "label": "GA4 Landing Pages",
            "tool": "fetch_ga4_landing_pages",
            "description": "Paid landing page behavior with engagement and conversion context.",
            "fields": {
                "landing_page": {"type": "dimension"},
                "sessions": {"type": "metric", "unit": "count", "agg": "sum"},
                "bounce_rate": {"type": "metric", "unit": "percent", "agg": "avg"},
                "engagement_rate": {"type": "metric", "unit": "percent", "agg": "avg"},
                "avg_session_duration_seconds": {"type": "metric", "unit": "seconds", "agg": "avg"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "revenue": {"type": "metric", "unit": "currency", "agg": "sum"},
            },
            "sortable_by": ["sessions", "bounce_rate", "conversions", "revenue"],
        },
        {
            "entity_id": "ga4_conversion_paths",
            "label": "GA4 Conversion Paths",
            "tool": "fetch_ga4_conversion_paths",
            "description": "Source/channel path context for assisted-conversion analysis.",
            "fields": {
                "source_medium": {"type": "dimension"},
                "default_channel_group": {"type": "dimension"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "revenue": {"type": "metric", "unit": "currency", "agg": "sum"},
                "sessions": {"type": "metric", "unit": "count", "agg": "sum"},
            },
            "sortable_by": ["conversions", "revenue", "sessions"],
        },
    ],
}
