"""Entity catalog for Google Search Console supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "gsc",
    "schema_version": "1.0.0",
    "last_audited": "2026-09-24",
    "api_version": "searchconsole-v1",
    "audit_notes": "Aligned with service/google/gsc.py response fields used by insight tools.",
    "entities": [
        {
            "entity_id": "gsc_query_performance",
            "label": "GSC Query Performance",
            "fetch_fn": "fetch_gsc_query_performance",
            "description": (
                "Organic queries, highest impressions first, with totals and impressions_coverage "
                "for the whole window. Queries Google anonymises are absent by design."
            ),
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
            "fetch_fn": "fetch_gsc_page_performance",
            "description": (
                "Organic pages, highest impressions first. Use page totals, not query sums, "
                "for how much organic traffic there is."
            ),
            "fields": {
                "page": {"type": "dimension"},
                "clicks": {"type": "metric", "unit": "count", "agg": "sum"},
                "impressions": {"type": "metric", "unit": "count", "agg": "sum"},
                "ctr": {"type": "metric", "unit": "percent", "agg": "avg"},
                "avg_position": {"type": "metric", "unit": "rank", "agg": "avg"},
            },
            "sortable_by": ["impressions", "clicks", "ctr", "avg_position"],
        },
        {
            "entity_id": "gsc_query_page",
            "label": "GSC Query × Page",
            "fetch_fn": "fetch_gsc_query_page",
            "description": (
                "Which page ranks for which query. The only view that shows cannibalisation "
                "(one query split across pages) or a query landing on the wrong page."
            ),
            "fields": {
                "query": {"type": "dimension"},
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
