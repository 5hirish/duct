"""Entity catalog for Google Search Console supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "gsc",
    "schema_version": "1.0.0",
    "last_audited": "2026-08-29",
    "api_version": "searchconsole-v1",
    "audit_notes": "Aligned with service/google/gsc.py response fields used by insight tools.",
    "entities": [
        {
            "entity_id": "gsc_query_performance",
            "label": "GSC Query Performance",
            "tool": "fetch_gsc_query_performance",
            "description": "Organic query performance with clicks, impressions, CTR, and position.",
            "fields": {
                "query": {"type": "dimension"},
                "clicks": {"type": "metric", "unit": "count", "agg": "sum"},
                "impressions": {"type": "metric", "unit": "count", "agg": "sum"},
                "ctr": {"type": "metric", "unit": "percent", "agg": "avg"},
                "avg_position": {"type": "metric", "unit": "rank", "agg": "avg"},
            },
            "sortable_by": ["impressions", "clicks", "ctr", "avg_position"],
        },
        {
            "entity_id": "gsc_page_performance",
            "label": "GSC Page Performance",
            "tool": "fetch_gsc_page_performance",
            "description": "Organic page-level performance with clicks, impressions, CTR, and position.",
            "fields": {
                "page": {"type": "dimension"},
                "clicks": {"type": "metric", "unit": "count", "agg": "sum"},
                "impressions": {"type": "metric", "unit": "count", "agg": "sum"},
                "ctr": {"type": "metric", "unit": "percent", "agg": "avg"},
                "avg_position": {"type": "metric", "unit": "rank", "agg": "avg"},
            },
            "sortable_by": ["impressions", "clicks", "ctr", "avg_position"],
        },
    ],
}
