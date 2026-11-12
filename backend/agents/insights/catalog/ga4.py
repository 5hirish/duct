"""Entity catalog for GA4 supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "ga4",
    "schema_version": "1.0.0",
    "last_audited": "2026-09-24",
    "api_version": "ga4-data-v1beta",
    "audit_notes": "Aligned with service/google/ga4.py response fields used by insight tools.",
    "entities": [
        {
            "entity_id": "ga4_landing_pages",
            "label": "GA4 Landing Pages",
            "fetch_fn": "fetch_ga4_landing_pages",
            "description": (
                "Landing-page behaviour per page and channel (GA4 default channel group: "
                "'Organic Search', 'Paid Search', 'Direct'...). Read only the channel your "
                "question is about."
            ),
            "fields": {
                "page_path": {"type": "dimension"},
                "channel": {"type": "dimension"},
                "sessions": {"type": "metric", "unit": "count", "agg": "sum"},
                "bounce_rate": {"type": "metric", "unit": "percent", "agg": "avg", "weight": "sessions"},
                "engagement_rate": {"type": "metric", "unit": "percent", "agg": "avg", "weight": "sessions"},
                "average_session_duration": {"type": "metric", "unit": "seconds", "agg": "avg", "weight": "sessions"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "total_revenue": {"type": "metric", "unit": "currency", "agg": "sum"},
            },
            "sortable_by": ["sessions", "bounce_rate", "conversions", "total_revenue"],
        },
        {
            "entity_id": "ga4_weekly_users",
            "label": "GA4 Weekly Active Users",
            "fetch_fn": "fetch_ga4_weekly_users",
            "description": (
                "Active users per ISO week (isoYearIsoWeek, e.g. 202645), oldest first. Users "
                "are not additive: never sum weeks into a total, and compare a week with weeks, "
                "not with a day or a month. The newest week is partial unless the window ends "
                "on a Sunday."
            ),
            "fields": {
                "iso_week": {"type": "dimension"},
                "active_users": {"type": "metric", "unit": "count"},
            },
            "sortable_by": ["iso_week", "active_users"],
        },
        {
            "entity_id": "ga4_conversion_paths",
            "label": "GA4 Conversion Paths",
            "fetch_fn": "fetch_ga4_conversion_paths",
            "description": "Source/channel path context for assisted-conversion analysis.",
            "fields": {
                "session_source_medium": {"type": "dimension"},
                "session_default_channel_group": {"type": "dimension"},
                "conversions": {"type": "metric", "unit": "count", "agg": "sum"},
                "total_revenue": {"type": "metric", "unit": "currency", "agg": "sum"},
                "sessions": {"type": "metric", "unit": "count", "agg": "sum"},
            },
            "sortable_by": ["conversions", "total_revenue", "sessions"],
        },
    ],
}
