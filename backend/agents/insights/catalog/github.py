"""Entity catalog for GitHub: what shipped, and when."""

from __future__ import annotations

# Literal on purpose, like every other catalog: scripts/build_integrations.py
# reads this dict with ast.literal_eval to build the integrations pages, so a
# name here (GITHUB_CONNECTOR_ID, WorkEventKind) breaks the site build.
# tests/test_github_connector.py holds the literals to those names.
ENTITY_CATALOG = {
    "connector_id": "github",
    "schema_version": "1.0.0",
    "last_audited": "2026-09-28",
    "api_version": "github-rest-2022-11-28",
    "audit_notes": "Aligned with service/github/fetch.py work-event rows.",
    "entities": [
        {
            "entity_id": "github_work_events",
            "label": "GitHub Work Events",
            "fetch_fn": "fetch_github",
            "description": (
                "What the project's repository shipped in the window, one row per event: "
                "releases, merged pull requests, closed issues, changed docs, then commits. "
                "Line a metric change up against merged_at and release times, not commit "
                "times, and a merge is not a deploy. File stats cover the newest commits "
                "only (all of them in a window of two days or less); the summary says how many."
            ),
            "fields": {
                "kind": {"type": "dimension", "values": ["commit", "pull_request", "issue", "release", "docs_change"]},
                "at": {"type": "dimension"},
                "ref": {"type": "dimension"},
                "title": {"type": "dimension"},
                "body": {"type": "dimension"},
                "author": {"type": "dimension"},
                "url": {"type": "dimension"},
                "state": {"type": "dimension"},
                "trailers": {"type": "dimension"},
                # Summed by Duct (agents/insights/totals.py) over the commits
                # that carry them; `truncated` marks the totals as a floor.
                "files_changed": {"type": "metric", "unit": "count", "agg": "sum"},
                "additions": {"type": "metric", "unit": "count", "agg": "sum"},
                "deletions": {"type": "metric", "unit": "count", "agg": "sum"},
            },
            "sortable_by": ["at", "additions", "deletions"],
        },
    ],
}
