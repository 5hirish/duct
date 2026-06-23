"""Canonical content-post metric contract — the SINGLE backend source of truth
for reading a post's ``perf`` dict.

``perf`` mixes three key conventions written over time: PostBridge's ``*_count``
keys (view_count/like_count/…), the migrated-MaxAura keys, and the canonical
manual-entry keys (views/likes/saves/…). Reading a metric means trying its
aliases in priority order — that mapping is THE contract and lives here once,
instead of being spelled out at every call site.

The frontend mirror is ``app/src/lib/contentMetrics.js`` (JS can't import this
Python module). Keep the two in sync — THIS file is the canonical contract; when
a key convention changes, update the alias map here and the JS mirror together.
"""

from __future__ import annotations

# Canonical metric name → the perf keys that may carry it, in priority order.
METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "views":           ("view_count", "views"),
    "likes":           ("like_count", "likes"),
    "comments":        ("comment_count", "comments"),
    "shares":          ("share_count", "shares"),
    "saves":           ("save_count", "saves"),
    "completion_rate": ("completion_rate",),
    "save_rate":       ("save_rate",),
    "profile_visits":  ("profile_visits",),
    "bio_link_clicks": ("bio_link_clicks",),
}


def _first_number(perf: dict | None, keys: tuple[str, ...]):
    for k in keys:
        v = (perf or {}).get(k)
        if isinstance(v, (int, float)):
            return v
    return None


def metric_int(perf: dict | None, name: str) -> int:
    """Read a metric as an int via its alias chain (0 if absent)."""
    v = _first_number(perf, METRIC_ALIASES.get(name, (name,)))
    return int(v) if isinstance(v, (int, float)) else 0


def metric_float(perf: dict | None, name: str) -> float:
    """Read a metric as a rounded float via its alias chain (0.0 if absent)."""
    v = _first_number(perf, METRIC_ALIASES.get(name, (name,)))
    return round(float(v), 3) if isinstance(v, (int, float)) else 0.0
