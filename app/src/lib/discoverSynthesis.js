// The "what's working" read-out above Discover's results.
//
// Computed in the browser from the posts already on screen, so it costs no
// Apify run and no model call, and it can never disagree with the grid below
// it. It answers the three calls a marketer makes from a result set: which
// format to make, which tags ride along, and which openings earned the most.
// Words live in the component; this module returns numbers and strings from
// the posts themselves.

// Tags so broad they top every niche's list and say nothing about this one.
const GENERIC_TAGS = new Set([
  "fyp", "foryou", "foryoupage", "fy", "fypシ", "viral", "trending", "xyzbca", "parati",
]);

export const TOP_HASHTAGS = 8;
export const WINNING_HOOKS = 3;

// A tag on one post of thirty is an accident, not a pattern.
const MIN_TAG_POSTS = 2;

// Long enough for a full opening line, short enough to stay one row wide.
const HOOK_MAX_CHARS = 90;

/** Interactions per view, the same measure the result cards show; 0 without views. */
export function engagement(post) {
  const plays = post?.play_count || 0;
  if (!plays) return 0;
  const acted = (post.digg_count || 0) + (post.comment_count || 0)
    + (post.share_count || 0) + (post.collect_count || 0);
  return acted / plays;
}

function median(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function normalizeTag(tag) {
  const name = typeof tag === "string" ? tag : tag?.name;
  return String(name || "").trim().replace(/^#/, "").toLowerCase();
}

/** A caption's opening line with its hashtags removed: the hook as the viewer met it. */
export function hookOf(text) {
  const firstLine = String(text || "").split("\n").find((line) => line.replace(/#[^\s#]+/g, "").trim()) || "";
  const hook = firstLine.replace(/#[^\s#]+/g, "").replace(/\s+/g, " ").trim();
  return hook.length > HOOK_MAX_CHARS ? `${hook.slice(0, HOOK_MAX_CHARS - 1).trimEnd()}…` : hook;
}

function formatShare(group, total) {
  return {
    count: group.length,
    share: total ? group.length / total : 0,
    // Median, not mean: one post at 40% engagement on 300 views would
    // otherwise decide which format "wins".
    engagement: median(group.map(engagement)),
  };
}

/**
 * The read-out for a result set, or null when there is nothing to read.
 * `exclude` is the tags that were searched for: every result carries them,
 * so they would top the list and teach nothing.
 */
export function synthesize(posts, { exclude = [] } = {}) {
  if (!posts?.length) return null;
  const total = posts.length;

  const skip = new Set([...GENERIC_TAGS, ...exclude.map(normalizeTag)]);
  const tagPosts = new Map();
  for (const post of posts) {
    for (const tag of new Set((post.hashtags || []).map(normalizeTag))) {
      if (tag && !skip.has(tag)) tagPosts.set(tag, (tagPosts.get(tag) || 0) + 1);
    }
  }
  const hashtags = [...tagPosts]
    .filter(([, count]) => count >= MIN_TAG_POSTS)
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
    .slice(0, TOP_HASHTAGS)
    .map(([tag, count]) => ({ tag, count }));

  // Engagement is a ratio, and a ratio on a few hundred views is noise. Only
  // posts that reached at least the set's median audience compete for a hook.
  const reach = median(posts.map((p) => p.play_count || 0));
  const hooks = posts
    .filter((p) => (p.play_count || 0) >= reach)
    .map((p) => ({ id: p.id, text: hookOf(p.text), engagement: engagement(p), plays: p.play_count || 0, url: p.web_video_url || "" }))
    .filter((h) => h.text && h.engagement > 0)
    .sort((a, b) => b.engagement - a.engagement)
    .slice(0, WINNING_HOOKS);

  return {
    total,
    engagement: median(posts.map(engagement)),
    slideshow: formatShare(posts.filter((p) => p.is_slideshow), total),
    video: formatShare(posts.filter((p) => !p.is_slideshow), total),
    hashtags,
    hooks,
  };
}
