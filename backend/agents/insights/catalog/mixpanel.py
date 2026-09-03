"""Entity catalog for Mixpanel supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "mixpanel",
    "schema_version": "1.0.0",
    "last_audited": "2026-08-31",
    "api_version": "mixpanel-query-2.0",
    "audit_notes": "Aligned with service/mixpanel/fetch.py summary/data fields.",
    "entities": [
        {
            "entity_id": "mixpanel_event_counts",
            "label": "Mixpanel Key Event Counts",
            "fetch_fn": "fetch_mixpanel",
            "description": (
                "Daily counts of the project's key events (signup/login/upgrade …) with "
                "internal traffic excluded, plus saved-funnel completion — the cross-platform "
                "reference to reconcile GA4 and ad-platform conversions against."
            ),
            "fields": {
                "key_events": {"type": "dimension"},
                "event_totals": {"type": "metric", "unit": "count", "agg": "sum"},
                "funnels": {"type": "dimension"},
                "internal_traffic_excluded": {"type": "dimension"},
            },
            "sortable_by": ["event_totals"],
        },
    ],
}
