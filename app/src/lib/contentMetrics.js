// Shared metric normalization for published content posts.
//
// Three writers populate a post's `perf` JSON with DIFFERENT key conventions:
//   - PostBridge sync  → view_count, like_count, comment_count, share_count
//   - migrated MaxAura → views, likes, comments, shares, saves, avgWatchTime, …
//   - manual entry     → the canonical keys below (matches the MaxAura set)
// so every read goes through one picker that tries each known alias in turn.
// PostBridge supplies only the first four counts; saves, reach, watch time,
// completion, retention and audience age are platform-native and hand-entered.

function pickNum(perf, ...keys) {
  for (const k of keys) {
    const v = perf?.[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

// The four counts PostBridge can sync, plus saves (always manual).
export function coreMetrics(perf = {}) {
  return {
    views:    pickNum(perf, "view_count", "play_count", "views"),
    likes:    pickNum(perf, "like_count", "digg_count", "likes"),
    comments: pickNum(perf, "comment_count", "comments"),
    shares:   pickNum(perf, "share_count", "shares"),
    saves:    pickNum(perf, "save_count", "collect_count", "saves"),
  };
}

// Platform-native scalars PostBridge never returns — all hand-entered.
export function extraMetrics(perf = {}) {
  return {
    reach:          pickNum(perf, "reach", "reach_count", "impressions", "impression_count"),
    profileViews:   pickNum(perf, "profileViews", "profile_views"),
    newFollowers:   pickNum(perf, "newFollowers", "new_followers", "follows", "follower_count"),
    avgWatchTime:   pickNum(perf, "avgWatchTime", "avg_watch_time"),         // seconds
    completionRate: pickNum(perf, "completionRate", "completion_rate",       // percent 0–100
                            "watchFullVideo", "watched_full_video"),
  };
}

function objOrNull(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : null;
}

// { slide1: 100, slide2: 62, … } — per-slide retention %.
export function retentionOf(perf = {}) {
  return objOrNull(perf?.retention);
}

// { "18-24": 53, "25-34": 22, … } — audience age split %.
export function audienceAgeOf(perf = {}) {
  return objOrNull(perf?.audienceAge ?? perf?.audience_age);
}

// Save rate + engagement rate as fractions (0–1). Computed live from the current
// numbers (so a manual saves edit updates them), falling back to any stored rate.
export function derivedRates(perf = {}) {
  const { views, likes, comments, shares, saves } = coreMetrics(perf);
  const saveRate =
    views && saves != null ? saves / views : pickNum(perf, "saveRate", "save_rate");
  const eng = (likes || 0) + (comments || 0) + (shares || 0) + (saves || 0);
  const engagementRate =
    views ? eng / views : pickNum(perf, "engagementRate", "engagement_rate");
  return { saveRate, engagementRate };
}

// True once any core number is present — used to flip "No metrics yet" copy.
export function hasAnyMetric(perf = {}) {
  return Object.values(coreMetrics(perf)).some((v) => v != null);
}

// PostBridge "owns" a post's core counts only when it published it. For those
// posts the core four are read-only (a sync would overwrite a manual edit);
// everywhere else (TikTok Studio, migrated plans) every field is hand-entered.
export function isPostBridgeBacked(post) {
  return Boolean(post?.post_bridge_post_id);
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

export function fmtCount(n) {
  if (n == null) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(n % 1e6 === 0 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(n % 1e3 === 0 ? 0 : 1).replace(/\.0$/, "") + "K";
  return n.toLocaleString();
}

// frac is a fraction (0–1); renders as a percent with one decimal.
export function fmtRate(frac) {
  if (frac == null || !Number.isFinite(frac)) return "—";
  return `${(frac * 100).toFixed(1).replace(/\.0$/, "")}%`;
}

// pct is already a percent number (0–100).
export function fmtPct(pct) {
  if (pct == null || !Number.isFinite(pct)) return "—";
  return `${Number(pct.toFixed(1))}%`;
}

export function fmtSeconds(s) {
  if (s == null || !Number.isFinite(s)) return "—";
  return `${Number(s.toFixed(1))}s`;
}

export function timeAgo(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(s)) return "";
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

// share_url comes from PostBridge (external) — only allow http(s) so a
// javascript:/data: URL can't ride into an <a href> (XSS).
export function safeHref(u) {
  if (typeof u !== "string" || !u) return null;
  try {
    const url = new URL(u, typeof window !== "undefined" ? window.location.origin : "https://getduct.ai");
    return /^https?:$/.test(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

// last_synced_at = PostBridge pull; manual_updated_at = hand-entered. Show the
// most recent of the two so "Updated …" reflects whatever changed last.
export function lastUpdatedAt(perf = {}) {
  const a = perf?.last_synced_at ? new Date(perf.last_synced_at).getTime() : 0;
  const b = perf?.manual_updated_at ? new Date(perf.manual_updated_at).getTime() : 0;
  const best = Math.max(a || 0, b || 0);
  return best ? new Date(best).toISOString() : null;
}
