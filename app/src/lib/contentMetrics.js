/**
 * A content post's metrics, read the same way everywhere.
 *
 * `perf` is written by three hands with three sets of names for one number:
 * PostBridge's sync (`view_count`), plans migrated from MaxAura (`views`,
 * `avgWatchTime`), and a person typing in what PostBridge cannot supply. Every
 * read goes through `METRIC_ALIASES`, which mirrors
 * backend/service/content_metrics.py — JavaScript cannot import the Python, so
 * backend/tests/test_content_metrics.py parses this table and fails when the
 * two differ, order included. Change both in the same commit.
 */

// Canonical name → perf keys that may carry it, highest priority first. The
// canonical name is also the manual-entry field and the key a typed value is
// stored under.
export const METRIC_ALIASES = Object.freeze({
  views:           ["view_count", "views", "play_count"],
  likes:           ["like_count", "likes", "digg_count"],
  comments:        ["comment_count", "comments"],
  shares:          ["share_count", "shares"],
  saves:           ["saves", "save_count", "collect_count"],
  reach:           ["reach"],
  avg_watch_time:  ["avg_watch_time", "avgWatchTime"],
  completion_rate: ["completion_rate", "completionRate"],
});

// What PostBridge's analytics carry, which the same test checks against its
// schema. On a post PostBridge published these sync on their own, so the form
// shows them rather than asking for them.
export const SYNCED_METRICS = Object.freeze(["views", "likes", "comments", "shares"]);

export const METRIC_NAMES = Object.freeze(Object.keys(METRIC_ALIASES));

function numberOrNull(v) {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** One metric through its alias chain, or null. */
export function metricValue(perf, name) {
  for (const key of METRIC_ALIASES[name] || []) {
    const v = numberOrNull(perf?.[key]);
    if (v != null) return v;
  }
  return null;
}

/** Every metric by canonical name: `{ views, likes, …, completion_rate }`. */
export function metricsOf(perf) {
  return Object.fromEntries(METRIC_NAMES.map((name) => [name, metricValue(perf, name)]));
}

/** PostBridge published it, so its counts sync. */
export function isSyncedPost(post) {
  return Boolean(post?.post_bridge_post_id);
}

/** The metrics a person may type in on this post. */
export function editableMetrics(post) {
  return isSyncedPost(post)
    ? METRIC_NAMES.filter((name) => !SYNCED_METRICS.includes(name))
    : METRIC_NAMES;
}

/** The later of the last sync and the last hand edit, or null. */
export function lastUpdatedAt(perf) {
  const times = [perf?.last_synced_at, perf?.manual_updated_at]
    .map((v) => (v ? new Date(v).getTime() : NaN))
    .filter(Number.isFinite);
  return times.length ? new Date(Math.max(...times)).toISOString() : null;
}

/** The form's starting values: each metric as the string an input holds. */
export function metricInputs(perf, names) {
  return Object.fromEntries(
    names.map((name) => {
      const v = metricValue(perf, name);
      return [name, v == null ? "" : String(v)];
    }),
  );
}

/**
 * What the form changed, as the body POST /metrics takes: a number for a new
 * or corrected value, null for one the person cleared. A field left as it was
 * is not sent: sending it would mark a synced or migrated number as typed-in,
 * and from then on no sync could refresh it.
 */
export function metricChanges(inputs, perf, names) {
  const out = {};
  for (const name of names) {
    const raw = String(inputs?.[name] ?? "").trim();
    const current = metricValue(perf, name);
    if (raw === "") {
      if (current != null) out[name] = null;
      continue;
    }
    const n = Number(raw);
    if (Number.isFinite(n) && n !== current) out[name] = n;
  }
  return out;
}
