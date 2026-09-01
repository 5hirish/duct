// The desk's routing rule, and the small amount of formatting it needs.
//
// Deliberately free of imports and IO so it can be exercised by
// `npm run check:desk` outside a browser — same arrangement as
// connectorCount.js and slideDoc.js.
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

export const BUCKETS = [
  { key: NEEDS_YOU, label: "Needs you", blurb: "Nothing here moves without you." },
  { key: FOUND, label: "What I found", blurb: "Checked, with the dates attached." },
  { key: IN_PROGRESS, label: "In progress", blurb: "Waiting on Duct or on the clock." },
];

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
  return conv?.status === "active" ? IN_PROGRESS : null;
}

/**
 * How sure Duct is, in words a person can act on.
 *
 * A memory the agent wrote but nobody has confirmed is NOT a warning — it is
 * simply not yet corroborated, and saying so is more honest than a green tick.
 */
export function certainty(row) {
  if (row?.status === "proposed") return { label: "Not confirmed", tone: "unsure" };
  if (row?.confidence === "high") return { label: "Checked", tone: "sure" };
  if (row?.confidence === "low") return { label: "Low confidence", tone: "unsure" };
  return { label: "Fairly sure", tone: "partial" };
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
 * a row came from: { id, type, title, detail, at, weight, href, tone }.
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
      detail: bucket === FOUND ? sure.label : "Nobody has closed this",
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
      title: set.title || "Untitled change set",
      detail:
        bucket === NEEDS_YOU
          ? `${count} change${count === 1 ? "" : "s"} to approve`
          : set.status === "applying"
            ? "Applying now"
            : "Approved, waiting to run",
      tone: bucket === NEEDS_YOU ? "alert" : "running",
      at: set.updated_at || set.created_at || "",
      // Above every memory: a change set is a mutation someone is waiting on.
      weight: 10,
      changeSetId: set.id,
    });
  }

  for (const conv of conversations) {
    if (routeConversation(conv) !== IN_PROGRESS) continue;
    out[IN_PROGRESS].push({
      id: `conversation:${conv.id}`,
      type: "conversation",
      title: conv.title || "Untitled thread",
      detail: "Pick up where you left off",
      tone: "running",
      at: conv.last_active_at || conv.created_at || "",
      weight: conv.pinned ? 9 : 6,
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
 * `tone` picks the colour; the caller owns the glyph.
 */
export function artifactLook(artifact) {
  const kind = (artifact?.kind || "").toLowerCase();
  const type = (artifact?.content_type || "").toLowerCase();
  if (kind === "brief" || type.includes("markdown")) {
    return { label: "Brief", tone: "brief" };
  }
  if (kind === "report") return { label: "Report", tone: "report" };
  if (type.includes("json") || type.includes("csv")) return { label: "Data", tone: "data" };
  if (type.startsWith("image/")) return { label: "Image", tone: "image" };
  return { label: kind ? kind[0].toUpperCase() + kind.slice(1) : "Document", tone: "data" };
}

/** Pinned first, then newest. The same order in both tabs. */
export function pinnedFirst(rows, at = (r) => r.created_at) {
  return [...rows].sort((a, b) => {
    if (Boolean(a.pinned) !== Boolean(b.pinned)) return a.pinned ? -1 : 1;
    return String(at(b) || "").localeCompare(String(at(a) || ""));
  });
}

// ---------------------------------------------------------------------------
// Words for times and totals
// ---------------------------------------------------------------------------

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "18 minutes ago" beats "08:42" on a page you read once a day. */
export function relativeTime(iso, now = Date.now()) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const delta = now - then;
  if (delta < 0) return "just now";
  if (delta < MINUTE) return "just now";
  if (delta < HOUR) {
    const n = Math.floor(delta / MINUTE);
    return `${n} minute${n === 1 ? "" : "s"} ago`;
  }
  if (delta < DAY) {
    const n = Math.floor(delta / HOUR);
    return `${n} hour${n === 1 ? "" : "s"} ago`;
  }
  if (delta < 2 * DAY) return "Yesterday";
  if (delta < 7 * DAY) return `${Math.floor(delta / DAY)} days ago`;
  return new Date(then).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/**
 * The one sentence at the top of the page.
 *
 * It states what is true, never what would be nice. When nothing is blocked it
 * says so plainly rather than inventing urgency, and when nothing has run yet
 * it admits that instead of reporting a zero as if it were a result.
 */
export function headline({ needsYou = 0, found = 0, lastRunAt = "", sourceCount = 0, now = Date.now() } = {}) {
  const parts = [];
  if (lastRunAt) parts.push(`Last checked ${relativeTime(lastRunAt, now)}.`);
  else parts.push("Nothing has run yet.");
  parts.push(`${sourceCount} source${sourceCount === 1 ? "" : "s"} connected.`);
  const sub = parts.join(" ");

  if (needsYou > 0) {
    return { title: `${needsYou} thing${needsYou === 1 ? "" : "s"} need${needsYou === 1 ? "s" : ""} you.`, sub };
  }
  if (found > 0) {
    return {
      title: "Nothing needs you right now.",
      sub: `${found} finding${found === 1 ? "" : "s"} on file. ${sub}`,
    };
  }
  return { title: "Nothing to report yet.", sub };
}
