"""The one contract for reading and writing a content post's ``perf``.

``perf`` is a JSON column written by three hands, each with its own names for
the same number: PostBridge's sync (``view_count``, ``like_count`` …), plans
migrated from MaxAura (``views``, ``avgWatchTime``, ``completionRate`` …), and a
person typing in what PostBridge cannot supply. Reading a metric therefore means
trying its aliases in order, and ``METRIC_ALIASES`` is the only place that order
is written down. ``app/src/lib/contentMetrics.js`` carries the same table for
the browser (JavaScript cannot import this file); ``tests/test_content_metrics.py``
parses it and fails when the two disagree, because an alias one side knows and
the other does not is a number that shows in one place and not the other.

Writing has one rule: **a number a person entered is never overwritten by a
sync.** ``merge_manual_metrics`` records which metrics were typed in under
``manual_keys``; ``merge_synced_metrics`` skips every alias of those.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Canonical name → the perf keys that may carry it, highest priority first. The
# canonical name is also the manual-entry API field and the key a typed value is
# stored under, so it is always one of its own aliases. For the four counts
# PostBridge syncs its own key leads, because the sync is the freshest writer of
# those; for the rest the canonical key leads, because a person is.
METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "views":           ("view_count", "views", "play_count"),
    "likes":           ("like_count", "likes", "digg_count"),
    "comments":        ("comment_count", "comments"),
    "shares":          ("share_count", "shares"),
    "saves":           ("saves", "save_count", "collect_count"),
    "reach":           ("reach",),
    "avg_watch_time":  ("avg_watch_time", "avgWatchTime"),     # seconds
    "completion_rate": ("completion_rate", "completionRate"),  # percent, 0–100
}

MANUAL_KEYS = "manual_keys"              # the metrics a person entered, by canonical name
MANUAL_UPDATED_AT = "manual_updated_at"
LAST_SYNCED_AT = "last_synced_at"

_METRIC_OF_KEY: dict[str, str] = {
    key: name for name, keys in METRIC_ALIASES.items() for key in keys
}

# Never taken from a sync payload: "id" is PostBridge's analytics row, not a
# metric, and the bookkeeping keys are this module's to write, not a vendor's.
_NOT_SYNCED = frozenset({"id", MANUAL_KEYS, MANUAL_UPDATED_AT})


def _number(value: Any) -> int | float | None:
    # bool is an int to Python; a stray True is not one view.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def metric_value(perf: Mapping[str, Any] | None, name: str) -> int | float | None:
    """A metric through its alias chain, or None when no alias holds a number."""
    for key in METRIC_ALIASES[name]:
        value = _number((perf or {}).get(key))
        if value is not None:
            return value
    return None


def manual_metrics(perf: Mapping[str, Any] | None) -> set[str]:
    """The metrics a person entered on this post."""
    return set((perf or {}).get(MANUAL_KEYS) or [])


def save_rate(perf: Mapping[str, Any] | None) -> float | None:
    """Saves per view as a fraction, derived from the current numbers.

    Derived rather than read, because nothing writes a rate: PostBridge sends
    views and a person types saves, so a stored ``save_rate`` exists only on
    migrated rows and is the fallback for them.
    """
    views = metric_value(perf, "views")
    saves = metric_value(perf, "saves")
    if views and saves is not None:
        return saves / views
    return _number((perf or {}).get("save_rate"))


def merge_manual_metrics(
    perf: Mapping[str, Any] | None,
    entered: Mapping[str, int | float | None],
    *,
    at: str,
) -> dict[str, Any]:
    """Merge hand-entered metrics into a copy of ``perf`` and mark them manual.

    A value replaces the metric, not just its canonical key: every other alias
    is dropped, or a stale ``view_count`` earlier in the chain would still be
    what every reader sees. ``None`` withdraws a manual value, and unmarks it so
    the next sync owns the metric again.
    """
    unknown = set(entered) - set(METRIC_ALIASES)
    if unknown:
        raise ValueError(f"not a content metric: {sorted(unknown)}")
    merged = dict(perf or {})
    manual = manual_metrics(merged)
    for name, value in entered.items():
        for key in METRIC_ALIASES[name]:
            merged.pop(key, None)
        if value is None:
            manual.discard(name)
        else:
            merged[name] = value
            manual.add(name)
    merged[MANUAL_KEYS] = sorted(manual)
    merged[MANUAL_UPDATED_AT] = at
    return merged


def merge_synced_metrics(
    perf: Mapping[str, Any] | None,
    synced: Mapping[str, Any],
    *,
    synced_at: str | None,
) -> dict[str, Any]:
    """Merge a PostBridge analytics payload into a copy of ``perf``.

    Keys that alias a metric a person entered are skipped, so a sync can add
    and refresh numbers but never replace one somebody typed. Anything else in
    the payload (share URL, cover, platform ids) is written through as before.
    """
    merged = dict(perf or {})
    manual = manual_metrics(merged)
    for key, value in synced.items():
        if value is None or key in _NOT_SYNCED:
            continue
        if _METRIC_OF_KEY.get(key) in manual:
            continue
        merged[key] = value
    merged[LAST_SYNCED_AT] = synced_at
    return merged
