// The desk's routing rule, and the small amount of formatting it needs.
//
// Deliberately free of imports and IO so it can be exercised by
// `npm run check:desk` outside a browser — same arrangement as
// connectorCount.js and slideDoc.js.
//
// It also carries no words. Everything here that reaches the screen is a
// code plus the data behind it (`{ code: "waiting" }`, `{ detailCode:
// "changes_to_approve", count: 3 }`); the components that render the desk own
// the sentences, through Lingui. The plain-node check above is why: it cannot
// run the `msg` macro, and a module that mixed English into its return values
// was the one part of the desk a Spanish user still read in English.
//
// ONE RULE. Every item lands in exactly one bucket, decided by a single
// question: *who is holding it?* Topic-based cards (a "goals" card, a
// "problems" card) put a blocked goal in two places at once, and the moment a
// count is wrong nobody reads a count again.
//
//   NEEDS_YOU   — cannot move without a person: an approval, a decision, an
//                 access grant. Never merely "unconfirmed".
//   FOUND       — waiting on nobody. A standing claim about the account.
//   IN_PROGRESS — waiting on Duct or on the clock.

export const NEEDS_YOU = "needs_you";
export const FOUND = "found";
export const IN_PROGRESS = "in_progress";

/** How many items one card shows before it starts counting the rest. */
export const CARD_LIMIT = 3;

// Memory kinds that state something about the account rather than narrate a
// step. `action` is absent on purpose: an in-flight action is IN_PROGRESS, and
// a finished one is history the timeline already carries.
const CLAIM_KINDS = new Set([
  "goal", "metric", "conclusion", "incident", "decision", "watch", "milestone", "status",
]);

/** Live = the current statement of its subject, not a closed or dismissed one. */
export function isLiveMemory(row) {
  if (!row) return false;
  if (row.superseded_by) return false;
  if (row.valid_to) return false;
  return row.status === "confirmed" || row.status === "proposed";
}

/** An incident nobody has closed is the one memory that blocks on a human. */
function isOpenIncident(row) {
  return isLiveMemory(row) && row.kind === "incident";
}

export function routeMemory(row) {
  if (!isLiveMemory(row)) return null;
  if (isOpenIncident(row)) return NEEDS_YOU;
  return CLAIM_KINDS.has(row.kind) ? FOUND : null;
}

export function routeChangeSet(set) {
  // `proposed` is the only status waiting on a person. `approved` has already
  // had its click and is waiting on Duct to run it.
  if (set?.status === "proposed") return NEEDS_YOU;
  if (set?.status === "approved" || set?.status === "applying") return IN_PROGRESS;
  return null;
}

export function routeConversation(conv) {
  if (conv?.status !== "active") return null;
  // What the run is doing decides the card: parked on the user or stopped on
  // a failure is theirs to deal with; anything else is simply open.
  if (conv.run_status === "paused" || conv.run_status === "failed") return NEEDS_YOU;
  return IN_PROGRESS;
}

/**
 * The desk card's line for a thread, from its run status, as a code the card
 * turns into words: `waiting` | `failed` | `working` | `stopped` | `resume`.
 * `error` is the backend's own message for a failed turn, and may be empty.
 */
export function conversationCard(conv) {
  switch (conv?.run_status) {
    case "paused":
      return { code: "waiting", tone: "attention", error: "" };
    case "failed":
      return { code: "failed", tone: "attention", error: conv.run_error?.error || "" };
    case "running":
      return { code: "working", tone: "running", error: "" };
    case "cancelled":
      return { code: "stopped", tone: "running", error: "" };
    default:
      return { code: "resume", tone: "running", error: "" };
  }
}

/**
 * How sure Duct is: `unconfirmed` | `checked` | `low` | `fair`.
 *
 * A memory the agent wrote but nobody has confirmed is NOT a warning — it is
 * simply not yet corroborated, and saying so is more honest than a green tick.
 */
export function certainty(row) {
  if (row?.status === "proposed") return { code: "unconfirmed", tone: "unsure" };
  if (row?.confidence === "high") return { code: "checked", tone: "sure" };
  if (row?.confidence === "low") return { code: "low", tone: "unsure" };
  return { code: "fair", tone: "partial" };
}

/**
 * A memory's number, when the agent stored one: `{ value, unit, delta }` from
 * the remember tool's typed payload (`{"value": 71, "unit": "USD", "delta":
 * 0.38}`), `delta` a ratio. Most memories have none, and the row's number
 * slot then holds nothing rather than a placeholder.
 */
export function figureOf(value) {
  const v = value?.value;
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  const delta = typeof value.delta === "number" && Number.isFinite(value.delta) ? value.delta : null;
  return { value: v, unit: typeof value.unit === "string" ? value.unit : "", delta };
}

/** The connector a memory was read from, when its provenance names one. */
export function sourceOf(refs) {
  for (const ref of Array.isArray(refs) ? refs : []) {
    if (ref && typeof ref.connector === "string" && ref.connector) return ref.connector;
  }
  return "";
}

/** Ranking inside a card: importance first, then how recently we learned it. */
function byWeight(a, b) {
  const ia = a.weight ?? 0;
  const ib = b.weight ?? 0;
  if (ia !== ib) return ib - ia;
  return String(b.at || "").localeCompare(String(a.at || ""));
}

/**
 * Fold the three sources into the three cards.
 *
 * Items are a common shape so a card renders one way regardless of which table
 * a row came from: { id, type, title, titleCode, detailCode, count, error,
 * at, weight, tone }.
 *
 * `title` is the row's own; when it has none, `titleCode` names the fallback
 * (`untitled_thread` | `untitled_change_set`). `detailCode` is one of the
 * certainty codes above, `unclosed` for an open incident,
 * `changes_to_approve` (with `count`) | `applying` | `approved` for a change
 * set, or a `conversationCard` code (with `error`) for a thread.
 */
export function buildDesk({ memories = [], changeSets = [], conversations = [] } = {}) {
  const out = { [NEEDS_YOU]: [], [FOUND]: [], [IN_PROGRESS]: [] };

  for (const row of memories) {
    const bucket = routeMemory(row);
    if (!bucket) continue;
    const sure = certainty(row);
    out[bucket].push({
      id: `memory:${row.id}`,
      type: "memory",
      kind: row.kind,
      title: row.title,
      body: row.body || "",
      detailCode: bucket === FOUND ? sure.code : "unclosed",
      tone: bucket === FOUND ? sure.tone : "alert",
      at: row.recorded_at || row.observed_at || "",
      weight: row.importance ?? 5,
      conversationId: row.conversation_id || "",
      memoryId: row.id,
      // What the subject is, for telling one fact from a restatement of it.
      subject: [row.kind, row.entity_key, row.attribute, row.period].join("|"),
      hasSubject: Boolean(row.entity_key),
      figure: figureOf(row.value),
      source: sourceOf(row.source_refs),
    });
  }

  for (const set of changeSets) {
    const bucket = routeChangeSet(set);
    if (!bucket) continue;
    const count = Array.isArray(set.changes) ? set.changes.length : 0;
    out[bucket].push({
      id: `change_set:${set.id}`,
      type: "change_set",
      title: set.title || "",
      titleCode: set.title ? "" : "untitled_change_set",
      detailCode:
        bucket === NEEDS_YOU
          ? "changes_to_approve"
          : set.status === "applying"
            ? "applying"
            : "approved",
      count,
      tone: bucket === NEEDS_YOU ? "alert" : "running",
      at: set.updated_at || set.created_at || "",
      // Above every memory: a change set is a mutation someone is waiting on.
      weight: 10,
      changeSetId: set.id,
    });
  }

  for (const conv of conversations) {
    const bucket = routeConversation(conv);
    if (!bucket) continue;
    const card = conversationCard(conv);
    out[bucket].push({
      id: `conversation:${conv.id}`,
      type: "conversation",
      title: conv.title || "",
      titleCode: conv.title ? "" : "untitled_thread",
      // A thread is titled with the first thing the person typed, verbatim
      // (routes/agents.py), so its title is their words, not Duct's.
      titleBy: "person",
      detailCode: card.code,
      error: card.error,
      tone: card.tone,
      at: conv.last_active_at || conv.created_at || "",
      // A thread waiting on its owner outranks one merely open.
      weight: (bucket === NEEDS_YOU ? 10 : 6) + (conv.pinned ? 3 : 0),
      conversationId: conv.id,
    });
  }

  for (const key of Object.keys(out)) out[key].sort(byWeight);
  return {
    needsYou: out[NEEDS_YOU],
    found: out[FOUND],
    inProgress: out[IN_PROGRESS],
  };
}

// ---------------------------------------------------------------------------
// The arrangement: one shape, whatever the agent wrote
// ---------------------------------------------------------------------------
//
// Everything on the desk is written at run time — by a model (findings,
// incidents, change sets) or by the person (a thread is titled with their
// first message) — so its count, length, mix and age are unknown when the
// page is designed. The three buckets above let that content decide the
// layout: seven items in one card beside one item in another, and an empty
// box beside both. The arrangement below gives the page a fixed shape
// instead (DESIGN.md, "Content awareness"):
//
//   - a state, which picks the headline, from a closed set of sentences;
//   - at most one lead item, picked by a score this module computes;
//   - at most QUEUE_LIMIT rows under it, then a count of the rest;
//   - what Duct knows as at most NOTES_LIMIT notes, the rest a link away;
//   - what Duct is doing as a count, never a card.
//
// Age and repetition are rules, not judgement: a waiting item older than
// FILE_AFTER_DAYS is filed (and counted), restatements of one fact merge.

/** Rows shown under the lead before the rest is counted. */
export const QUEUE_LIMIT = 4;
/** Findings shown on the desk; the project's memory page holds the rest. */
export const NOTES_LIMIT = 3;
/** A waiting item this old is filed away rather than shown. */
export const FILE_AFTER_DAYS = 14;
/** A finding this old is no longer news. */
export const NOTE_FRESH_DAYS = 30;
/** Duct not having looked for this long is the first thing worth saying. */
export const STALE_AFTER_DAYS = 7;

/** The closed set of things the page can be. Each has one headline. */
export const DESK_STATE = {
  CONNECT: "connect", // nothing connected
  WORKING: "working", // Duct is looking and nothing waits on you
  STALE: "stale", // Duct has not looked in a while
  NEEDS_YOU: "needs_you",
  CLEAR: "clear", // Duct has looked and nothing waits on you
  NOTHING: "nothing", // connected, never run
};

// What makes a waiting item urgent, before importance and age. A run parked on
// a question is the most blocked thing there is; a failed run can be retried
// whenever, so it ranks below a problem in the data.
const URGENCY = { waiting: 30, changes_to_approve: 28, unclosed: 20, failed: 10 };
const SURE = { checked: 2, fair: 1, low: 0, unconfirmed: 0 };
// The verb a row leads with, by what the person would do about it. A code: the
// component owns the word.
const VERB = { waiting: "answer", changes_to_approve: "approve", unclosed: "review", failed: "retry" };
const WORKING_CODES = new Set(["working", "applying", "approved"]);

function ageDays(iso, now) {
  const t = Date.parse(iso || "");
  return Number.isNaN(t) ? 0 : Math.max(0, (now - t) / DAY);
}

const STOPWORDS = new Set(
  ("the and for are but not you your our its this that with from into over than " +
    "was were has have had will can all any per via out off").split(" ")
);

/** A title's content words, folded so that "pages" and "page" agree. */
export function titleWords(title) {
  return String(title || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^\p{L}\p{N}]+/u)
    .filter((w) => w.length > 2 && !STOPWORDS.has(w) && !/^\d/.test(w))
    .map((w) => (w.length > 4 && w.endsWith("s") ? w.slice(0, -1) : w));
}

function titleNumbers(title) {
  return (String(title || "").match(/\d+(?:[.,]\d+)?/g) || []).join(" ");
}

/**
 * Are two findings the same fact, said twice?
 *
 * The same stored subject is the strong signal. Without one, the words: at
 * least three shared and a Dice overlap of 0.6. Numbers veto it — "sessions
 * fell 12%" and "sessions fell 8%" share every word and are two facts, and a
 * merge that hid one would be the desk lying. Titles with no spaces (Japanese)
 * yield few words and so never merge, which is the safe way to be wrong.
 */
export function sameFinding(a, b) {
  if (a.hasSubject && b.hasSubject) return a.subject === b.subject;
  if (titleNumbers(a.title) !== titleNumbers(b.title)) return false;
  const A = new Set(titleWords(a.title));
  const B = new Set(titleWords(b.title));
  let shared = 0;
  for (const w of A) if (B.has(w)) shared += 1;
  return shared >= 3 && (2 * shared) / (A.size + B.size) >= 0.6;
}

/**
 * Two threads opened with the same words are, on the desk, one thread. Joined
 * without spaces, because the person typed it: "webperformance" and
 * "web-performance" are one word spelled twice.
 */
function sameThread(a, b) {
  const wa = titleWords(a.title).join("");
  return Boolean(wa) && wa === titleWords(b.title).join("");
}

function alike(a, b) {
  if (a.type !== b.type) return false;
  if (a.type === "memory") return sameFinding(a, b);
  if (a.type === "conversation") return sameThread(a, b);
  return false; // two change sets are two mutations, whatever they are called
}

/** Keep the first of each run of alike items (the list is ranked), counting the rest. */
function mergeAlike(items) {
  const kept = [];
  for (const item of items) {
    const twin = kept.find((k) => alike(k, item));
    if (twin) twin.copies += 1;
    else kept.push({ ...item, copies: 1 });
  }
  return kept;
}

/**
 * "6 weeks ago", for how long Duct has not looked. Weeks then months: the
 * one place a duration reads better than `relativeTime`'s date.
 */
export function elapsed(iso, { now = Date.now(), locale } = {}) {
  if (!iso || Number.isNaN(Date.parse(iso))) return "";
  const days = Math.floor(ageDays(iso, now));
  const rtf = new Intl.RelativeTimeFormat(locale || undefined, { numeric: "auto" });
  if (days < 14) return rtf.format(-days, "day");
  if (days < 60) return rtf.format(-Math.floor(days / 7), "week");
  return rtf.format(-Math.floor(days / 30), "month");
}

/**
 * The whole desk, arranged.
 *
 * Takes what `loadDesk` returns and answers everything the page draws, so the
 * page holds no rule of its own and every rule here can be asserted on in
 * plain Node against generated content (`lib/__fixtures__/deskScenarios.mjs`).
 *
 * Returns `{ state, lead, rows, more, filed, notes, notesTotal, working,
 * waiting, lookedAt, hasRun, sourceCount }`. `lead` is an item or null;
 * `rows` are at most QUEUE_LIMIT; `more` is the rest of the queue, `filed`
 * the waiting items too old to show. `waiting` counts what the headline says
 * needs you: shown and counted, never filed.
 */
export function arrangeDesk(
  { memories = [], changeSets = [], conversations = [], activity = [], sourceCount = 0 } = {},
  { now = Date.now() } = {}
) {
  const desk = buildDesk({ memories, changeSets, conversations });

  const scored = desk.needsYou
    .map((item) => ({
      ...item,
      verb: VERB[item.detailCode] || "review",
      score: (URGENCY[item.detailCode] ?? 0) + (item.weight ?? 5) - ageDays(item.at, now),
    }))
    .sort((a, b) => b.score - a.score);
  const merged = mergeAlike(scored);
  const queue = merged.filter((i) => !i.at || ageDays(i.at, now) <= FILE_AFTER_DAYS);
  const filed = merged.filter((i) => i.at && ageDays(i.at, now) > FILE_AFTER_DAYS);

  // A note that restates a waiting item adds nothing: the waiting item says it.
  const waitingFindings = merged.filter((i) => i.type === "memory");
  const allNotes = mergeAlike(
    desk.found
      .map((item) => ({
        ...item,
        score: (item.weight ?? 5) * 2 + (SURE[item.detailCode] ?? 0) - ageDays(item.at, now) / 2,
      }))
      .sort((a, b) => b.score - a.score)
  ).filter((note) => !waitingFindings.some((w) => sameFinding(w, note)));
  const notes = allNotes
    .filter((n) => !n.at || ageDays(n.at, now) <= NOTE_FRESH_DAYS)
    .slice(0, NOTES_LIMIT);

  const working = desk.inProgress.filter((i) => WORKING_CODES.has(i.detailCode));

  // When Duct last looked: its newest activity, or the newest thing it wrote,
  // whichever is later — a finding recorded in yesterday's chat is a look.
  let lookedAt = "";
  for (const s of [
    activity[0]?.created_at,
    ...memories.map((m) => m.recorded_at),
    ...conversations.map((c) => c.last_active_at),
  ]) {
    const t = Date.parse(s || "");
    if (!Number.isNaN(t) && (!lookedAt || t > Date.parse(lookedAt))) lookedAt = s;
  }
  const hasRun = activity.length > 0 || Boolean(lookedAt);

  const state =
    sourceCount === 0
      ? DESK_STATE.CONNECT
      : working.length && !queue.length
        ? DESK_STATE.WORKING
        : lookedAt && ageDays(lookedAt, now) > STALE_AFTER_DAYS && !working.length
          ? DESK_STATE.STALE
          : queue.length
            ? DESK_STATE.NEEDS_YOU
            : hasRun
              ? DESK_STATE.CLEAR
              : DESK_STATE.NOTHING;

  // The lead is a waiting item only when waiting items are the news. In the
  // other states the page leads with its own card (connect, a fresh look),
  // and the queue is plain rows under it.
  const leadFromQueue = state === DESK_STATE.NEEDS_YOU;
  const lead = leadFromQueue ? queue[0] : null;
  const rest = leadFromQueue ? queue.slice(1) : queue;

  return {
    state,
    lead,
    rows: rest.slice(0, QUEUE_LIMIT),
    more: rest.slice(QUEUE_LIMIT),
    filed,
    notes,
    notesTotal: allNotes.length,
    working,
    waiting: queue.length,
    lookedAt,
    hasRun,
    sourceCount,
  };
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

/**
 * The tile shown beside an artifact: type at a glance, before the words.
 * `tone` picks the colour; `code` picks the label (`brief` | `report` |
 * `data` | `image` | `document`, or `kind` when the artifact's own kind is
 * the best word for it, in which case `kind` carries that raw string); the
 * caller owns the glyph and the words.
 */
export function artifactLook(artifact) {
  const kind = (artifact?.kind || "").toLowerCase();
  const type = (artifact?.content_type || "").toLowerCase();
  if (kind === "brief" || type.includes("markdown")) {
    return { code: "brief", kind, tone: "brief" };
  }
  if (kind === "report") return { code: "report", kind, tone: "report" };
  if (type.includes("json") || type.includes("csv")) return { code: "data", kind, tone: "data" };
  if (type.startsWith("image/")) return { code: "image", kind, tone: "image" };
  return { code: kind ? "kind" : "document", kind, tone: "data" };
}

/** Pinned first, then newest. The same order in both tabs. */
export function pinnedFirst(rows, at = (r) => r.created_at) {
  return [...rows].sort((a, b) => {
    if (Boolean(a.pinned) !== Boolean(b.pinned)) return a.pinned ? -1 : 1;
    return String(at(b) || "").localeCompare(String(at(a) || ""));
  });
}

// ---------------------------------------------------------------------------
// Times and totals
// ---------------------------------------------------------------------------

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * "18 minutes ago" beats "08:42" on a page you read once a day.
 *
 * Rendered by `Intl` in the interface language: minutes and hours, then days
 * (`numeric: "auto"` says "yesterday" for one), then a short date once it is
 * more than a week old. Returns `""` both for no usable timestamp and for
 * under a minute — the one word `Intl` does not have is "just now", so the
 * caller renders that when it passed a timestamp and got nothing back. A
 * clock skew (the timestamp in the future) reads as under a minute, never as
 * the future.
 */
export function relativeTime(iso, { now = Date.now(), locale } = {}) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const delta = now - then;
  if (delta < MINUTE) return "";
  const lang = locale || undefined;
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  if (delta < HOUR) return rtf.format(-Math.floor(delta / MINUTE), "minute");
  if (delta < DAY) return rtf.format(-Math.floor(delta / HOUR), "hour");
  if (delta < 7 * DAY) return rtf.format(-Math.floor(delta / DAY), "day");
  return new Date(then).toLocaleDateString(lang, { day: "numeric", month: "short" });
}
