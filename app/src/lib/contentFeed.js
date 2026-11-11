/**
 * Planning from shipped work (#561): the setup sheet's options, the session
 * URL they travel in, the request body they become, and the words for what
 * the read step left out.
 *
 * The backend's half is `agents/content/feed.py` (FeedOptions, LeftOut). The
 * option values here are its wire values. No words here: `contentApi.js`
 * imports this, and plain-Node checks import that, where no macro runs. The
 * labels are `contentFeedLabels.js`.
 */

import { dayKey } from "./format.js";

export const FeedSource = Object.freeze({ GITHUB: "github", DUCT: "duct" });

export const Disclosure = Object.freeze({
  RELEASES: "releases",
  SHIPPED: "shipped",
  EVERYTHING: "everything",
});

// "Since last time" is no look-back at all: the backend starts where the last
// plan from shipped work ended, or a fortnight back the first time.
export const SINCE_LAST = 0;
export const LOOK_BACK_OPTIONS = [SINCE_LAST, 7, 14, 30];
export const HORIZON_OPTIONS = [7, 14];
export const MAX_DAYS_OPTIONS = [1, 2, 3, 4];

export const DEFAULT_FEED = Object.freeze({
  sources: [FeedSource.GITHUB, FeedSource.DUCT],
  lookBack: SINCE_LAST,
  horizon: 7,
  maxDays: 2,
  disclosure: Disclosure.SHIPPED,
});

const clamp = (value, options, fallback) => (options.includes(value) ? value : fallback);

/** The options a URL carries, back into the sheet's shape. Unknown values fall back. */
export function feedFromParams(params) {
  if (params.get("source") !== "work") return null;
  const sources = (params.get("sources") || "")
    .split(",")
    .filter((s) => Object.values(FeedSource).includes(s));
  return {
    sources: sources.length ? sources : [...DEFAULT_FEED.sources],
    lookBack: clamp(Number(params.get("look")) || SINCE_LAST, LOOK_BACK_OPTIONS, SINCE_LAST),
    horizon: clamp(Number(params.get("days")) || DEFAULT_FEED.horizon, HORIZON_OPTIONS, DEFAULT_FEED.horizon),
    maxDays: clamp(Number(params.get("max")) || DEFAULT_FEED.maxDays, MAX_DAYS_OPTIONS, DEFAULT_FEED.maxDays),
    disclosure: clamp(params.get("disclosure"), Object.values(Disclosure), DEFAULT_FEED.disclosure),
  };
}

/** The plan session for these options, from `today` for `horizon` days. */
export function feedSessionHref(options, today = new Date()) {
  const o = { ...DEFAULT_FEED, ...options };
  const params = new URLSearchParams({
    source: "work",
    start: dayKey(today),
    days: String(o.horizon),
    max: String(o.maxDays),
    disclosure: o.disclosure,
    sources: o.sources.join(","),
  });
  if (o.lookBack) params.set("look", String(o.lookBack));
  return `/content/sessions/new?${params}`;
}

/** What the backend's PlanRequest.feed takes. */
export function feedRequest(options) {
  const o = { ...DEFAULT_FEED, ...options };
  return {
    sources: o.sources,
    max_days: o.maxDays,
    disclosure: o.disclosure,
    ...(o.lookBack ? { look_back_days: o.lookBack } : {}),
  };
}

/**
 * The read step's payload as the summary draws it: the left-out reasons
 * biggest first, and the totals. Tolerates a missing or partial payload.
 */
export function feedSummary(payload) {
  const leftOut = Object.entries(payload?.left_out || {})
    .filter(([, n]) => Number(n) > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([reason, count]) => ({ reason, count: Number(count) }));
  const items = Array.isArray(payload?.items) ? payload.items : [];
  return {
    worth: Boolean(payload?.worth_a_plan),
    items,
    leftOut,
    leftOutTotal: leftOut.reduce((sum, r) => sum + r.count, 0),
    from: payload?.window?.from || "",
    to: payload?.window?.to || "",
    notes: Array.isArray(payload?.notes) ? payload.notes : [],
  };
}

/** The feed's sources on a plan day, when it has any. */
export function daySources(day) {
  return Array.isArray(day?.sources) ? day.sources.filter((s) => s && s.ref) : [];
}

/** How many of a plan's days were planned from shipped work. */
export function feedDayCount(days) {
  return (Array.isArray(days) ? days : []).filter((d) => daySources(d).length > 0).length;
}

/** The stored transcript row that carries the read step, if the thread has one. */
export function feedFromHistory(events) {
  const row = [...(events || [])].reverse().find((e) => e?.kind === "feed");
  return row?.data || null;
}

// The setup sheet's window drawing: how many day cells "since last time" is
// drawn as, since it has no fixed length (the label says which it is).
export const SINCE_LAST_CELLS = 7;

/**
 * The setup sheet's window as cells, for the drawing beside the answers:
 * the days read (each a day of work), today, and the days ahead, with the
 * ones a story may land on spread across them. Codes only; the sheet draws.
 */
export function feedRibbon({ lookBack, horizon, maxDays } = {}) {
  const past = lookBack === SINCE_LAST || !lookBack ? SINCE_LAST_CELLS : Math.max(1, Number(lookBack));
  const ahead = Math.max(1, Number(horizon) || 7);
  const stories = Math.min(ahead, Math.max(0, Number(maxDays) || 0));
  const lit = new Set(Array.from({ length: stories }, (_, i) => Math.floor(((i + 0.5) * ahead) / stories)));
  return {
    past: Array.from({ length: past }, (_, i) => ({ i, work: workAt(i, past) })),
    ahead: Array.from({ length: ahead }, (_, i) => ({ i, story: lit.has(i) })),
  };
}

// A fixed scatter of "days with work" on the read side: the same picture on
// every render, about two days in five, weighted to the recent end.
function workAt(i, n) {
  const fromToday = n - 1 - i;
  return (fromToday * 7 + 3) % 5 < 2 ? KIND_SCATTER[fromToday % KIND_SCATTER.length] : null;
}
// No release here: terracotta is the story days' colour on this drawing, and a
// read day drawn in it would look like a day already planned.
const KIND_SCATTER = ["pull_request", "commit", "change_set", "pull_request", "docs_change", "commit"];

// More stones than this stop reading as items and start reading as texture.
export const SIEVE_MAX = 60;

/**
 * Everything a read saw, one stone each: kept items in their kind, then the
 * left-out ones by reason, biggest reason first. Past SIEVE_MAX the left-out
 * stones are cut first (the kept ones are what the reader acts on), and
 * `hidden` says how many were not drawn.
 */
export function sieveStones(summary) {
  const s = summary || {};
  const kept = (s.items || []).map((it, i) => ({ key: `k-${it.ref || i}`, kind: it.kind || "", kept: true }));
  const room = Math.max(0, SIEVE_MAX - kept.length);
  const left = [];
  for (const { reason, count } of s.leftOut || []) {
    for (let n = 0; n < count && left.length < room; n += 1) left.push({ key: `l-${reason}-${n}`, reason, kept: false });
  }
  const shownKept = kept.slice(0, SIEVE_MAX);
  const total = (s.items || []).length + (s.leftOutTotal || 0);
  return { stones: [...shownKept, ...left], hidden: Math.max(0, total - shownKept.length - left.length), total };
}

/** The kept items counted by kind, biggest first: the summary's one-line tally. */
export function kindCounts(items) {
  const counts = new Map();
  for (const it of items || []) counts.set(it?.kind || "", (counts.get(it?.kind || "") || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([kind, count]) => ({ kind, count }));
}
