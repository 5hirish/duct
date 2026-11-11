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
