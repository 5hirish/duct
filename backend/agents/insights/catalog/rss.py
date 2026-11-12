"""Entity catalog for RSS and Atom feeds: what the project published (#564)."""

from __future__ import annotations

# Literal on purpose, like every other catalog: scripts/build_integrations.py
# reads this dict with ast.literal_eval to build the integrations pages.
ENTITY_CATALOG = {
    "connector_id": "rss",
    "schema_version": "1.0.0",
    "last_audited": "2026-11-12",
    "api_version": "rss-2.0-atom-1.0",
    "audit_notes": "Aligned with service/rss/fetch.py entry rows.",
    "entities": [
        {
            "entity_id": "rss_items",
            "label": "Feed Items",
            "fetch_fn": "fetch_rss",
            "description": (
                "Entries published in the window across every feed the project reads, newest "
                "first: a blog, a Substack, a changelog page, YouTube uploads, a repository's "
                "releases.atom. A feed lists only its newest entries, so an older window can come "
                "back short; the summary counts are per window, not the feed's history. The "
                "summary is the feed's own, clipped, never the article."
            ),
            "fields": {
                "feed": {"type": "dimension"},
                "feed_url": {"type": "dimension"},
                "title": {"type": "dimension"},
                "link": {"type": "dimension"},
                "published": {"type": "dimension"},
                "summary": {"type": "dimension"},
            },
            "sortable_by": ["published"],
        },
    ],
}
