"""Entity catalog for GrowthBook supplementary analysis."""

from __future__ import annotations

ENTITY_CATALOG = {
    "connector_id": "growthbook",
    "schema_version": "1.0.0",
    "last_audited": "2026-08-31",
    "api_version": "growthbook-v1",
    "audit_notes": "Aligned with service/growthbook/fetch.py experiment/result rows.",
    "entities": [
        {
            "entity_id": "growthbook_experiments",
            "label": "GrowthBook Experiments",
            "fetch_fn": "fetch_growthbook",
            "description": (
                "Experiments with status, phases, variations, and per-metric results for "
                "running ones. `stale_running` flags experiments still marked running whose "
                "exposures may have stopped — verify before citing."
            ),
            "fields": {
                "experiments": {"type": "dimension"},
                "results": {"type": "dimension"},
                "status": {"type": "dimension"},
                "stale_running": {"type": "dimension"},
                "running": {"type": "metric", "unit": "count", "agg": "sum"},
                "feature_count": {"type": "metric", "unit": "count", "agg": "sum"},
            },
            "sortable_by": ["running"],
        },
    ],
}
