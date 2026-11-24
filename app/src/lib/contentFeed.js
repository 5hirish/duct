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

// Linear and Notion are the user's own trusted MCP connections (#565),
// offered only when connected; their preset ids are these same values.
export const FeedSource = Object.freeze({
  GITHUB: "github", DUCT: "duct", LINEAR: "linear", NOTION: "notion",
  // The project's own feeds (#564), always offered: a source with nothing
  // connected leaves a note, never a failed read. Milestones (round star
  // counts, a best GA4 week) are no longer offered: a "we hit 1,000 stars"
  // post is not what a marketer or a shop owner plans from. A schedule saved
  // with it still runs, because the backend still reads it.
  RSS: "rss",
});
export const MCP_FEED_SOURCES = Object.freeze([FeedSource.LINEAR, FeedSource.NOTION]);

// Where a project's code lives, each its own source on the wire because the
// backend reads each host differently. The sheet shows them as one "Source
// code" tile with a picker, so a second host is an entry here and a reader in
// agents/content/feed.py, not another tile.
export const SOURCE_CODE_HOSTS = Object.freeze([FeedSource.GITHUB]);

/** The source-code host among `sources`, or null when none is ticked. */
export function codeHostOf(sources) {
  return SOURCE_CODE_HOSTS.find((h) => (sources || []).includes(h)) || null;
}

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
  notionDatabase: "",
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
    notionDatabase: (params.get("notion") || "").slice(0, 500),
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
  if (o.sources.includes(FeedSource.NOTION) && o.notionDatabase) params.set("notion", o.notionDatabase);
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
    ...(o.sources.includes(FeedSource.NOTION) && o.notionDatabase ? { notion_database: o.notionDatabase } : {}),
  };
}

/**
 * The sources the sheet may offer: GitHub and Duct always, Linear and Notion
 * when the person has them connected (`connected` is their server rows'
 * preset ids).
 */
export function offeredSources(connected) {
  const have = new Set(Array.isArray(connected) ? connected : []);
  return [
    ...SOURCE_CODE_HOSTS, FeedSource.DUCT, FeedSource.RSS,
    ...MCP_FEED_SOURCES.filter((s) => have.has(s)),
  ];
}

/** Why the sheet cannot start yet, as a code, or null. */
export function feedBlocker(options) {
  const o = { ...DEFAULT_FEED, ...options };
  if (!o.sources.length) return "no_source";
  if (o.sources.includes(FeedSource.NOTION) && !String(o.notionDatabase || "").trim()) return "no_notion_database";
  return null;
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

/**
 * What a day planned from shipped work teaches its reader: the idea its
 * brief carries, written by the plan in the brand's content language, so it
 * is shown as written and never translated. "" for any other day.
 */
export function dayIdea(day) {
  const idea = day?.brief?.idea;
  return typeof idea === "string" ? idea.trim() : "";
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
