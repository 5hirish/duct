"""Entity catalog for Microsoft Clarity supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "clarity",
    "schema_version": "1.0.0",
    "last_audited": "2026-08-31",
    "api_version": "clarity-export-data-v1",
    "audit_notes": "Aligned with service/clarity/fetch.py normalised blocks.",
    "entities": [
        {
            "entity_id": "clarity_friction",
            "label": "Clarity Landing-Page Friction",
            "tool": "fetch_clarity",
            "description": (
                "Last 1–3 days of on-page friction — rage clicks, dead clicks, quick-backs, "
                "script errors — overall and per URL, with traffic and engagement context. "
                "Costs 2 of the project's 10 daily API calls."
            ),
            "fields": {
                "traffic": {"type": "dimension"},
                "engagement": {"type": "dimension"},
                "friction": {"type": "dimension"},
                "pages": {"type": "dimension"},
                "friction_by_url": {"type": "dimension"},
                "sessions": {"type": "metric", "unit": "count", "agg": "sum"},
                "rage_click_sessions_pct": {"type": "metric", "unit": "percent", "agg": "avg"},
                "dead_click_sessions_pct": {"type": "metric", "unit": "percent", "agg": "avg"},
            },
            "sortable_by": ["sessions", "rage_click_sessions_pct", "dead_click_sessions_pct"],
        },
    ],
}
