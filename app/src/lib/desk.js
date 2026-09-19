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
      detailCode: bucket === FOUND ? sure.code : "unclosed",
      tone: bucket === FOUND ? sure.tone : "alert",
      at: row.recorded_at || row.observed_at || "",
      weight: row.importance ?? 5,
      conversationId: row.conversation_id || "",
      memoryId: row.id,
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

/** The three things the top of the page can say. */
export const HEADLINE_NEEDS_YOU = "needs_you";
export const HEADLINE_CLEAR = "clear";
export const HEADLINE_NOTHING = "nothing";

/**
 * The facts behind the one sentence at the top of the page.
 *
 * It states what is true, never what would be nice. When nothing is blocked it
 * says so plainly rather than inventing urgency (`clear`), and when nothing
 * has run yet it admits that (`hasRun` false) instead of reporting a zero as
 * if it were a result. `state` is which of the three sentences applies; the
 * counts and `lastRunAt` are what that sentence and its sub line are made of.
 */
export function headline({ needsYou = 0, found = 0, lastRunAt = "", sourceCount = 0 } = {}) {
  const state =
    needsYou > 0 ? HEADLINE_NEEDS_YOU : found > 0 ? HEADLINE_CLEAR : HEADLINE_NOTHING;
  return { state, needsYou, found, hasRun: Boolean(lastRunAt), lastRunAt, sourceCount };
}
