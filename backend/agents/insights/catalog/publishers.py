"""Entity catalog for the project's social schedulers (PostBridge, Zernio).

Not a connector in ``service/connectors.py``: a scheduler is a vendor key the
project's owner brings (``service/vendor_keys.py``), resolved by
``service/publishers/registry.py``, so ``fetchers.py`` dispatches this one
through ``service/publishers/metrics.py`` rather than through connector
credentials. The catalog shape is the same so the prompt, the totals and the
verifier treat its rows like any other source's.
"""

from __future__ import annotations

#: The ``connector_id`` the agent sees. Also the id the report picker uses for
#: "the posting side", whichever scheduler holds the accounts.
PUBLISHERS_SOURCE = "publishers"

SOCIAL_POST_METRICS = "social_post_metrics"

# Literal strings inside the catalog, not the constants above:
# scripts/build_integrations.py reads every ENTITY_CATALOG with
# ast.literal_eval, which cannot follow a name.
ENTITY_CATALOG = {
    "connector_id": "publishers",
    "schema_version": "1.0.0",
    "last_audited": "2026-11-09",
    "api_version": "duct-publishers-v1",
    "audit_notes": "Rows are service/publishers/metrics.as_rows over ReportedPost; every scheduler adapter maps into that shape.",
    "entities": [
        {
            "entity_id": "social_post_metrics",
            "label": "Social posts — views, likes, comments, shares",
            "fetch_fn": "fetch_social_post_metrics",
            "description": (
                "Every post on the accounts the project's schedulers hold, whoever published it, "
                "with the platform's own lifetime counts as of the last sync. Counts are per post "
                "for its whole life, not per day; posted_at is when it went out, and the window "
                "keeps the posts published inside it. engagement is likes + comments + shares."
            ),
            "fields": {
                "platform": {"type": "dimension"},
                "publisher": {"type": "dimension"},
                "title": {"type": "dimension"},
                "url": {"type": "dimension"},
                "posted_at": {"type": "dimension"},
                "views": {"type": "metric", "unit": "count", "agg": "sum"},
                "likes": {"type": "metric", "unit": "count", "agg": "sum"},
                "comments": {"type": "metric", "unit": "count", "agg": "sum"},
                "shares": {"type": "metric", "unit": "count", "agg": "sum"},
                "engagement": {"type": "metric", "unit": "count", "agg": "sum"},
                "engagement_rate": {"type": "metric", "unit": "percent", "agg": "avg", "ratio": ["engagement", "views"]},
            },
            "sortable_by": ["views", "engagement", "engagement_rate", "posted_at"],
        },
    ],
}

assert ENTITY_CATALOG["connector_id"] == PUBLISHERS_SOURCE
assert ENTITY_CATALOG["entities"][0]["entity_id"] == SOCIAL_POST_METRICS
