"use client";

// Shared date model for the plan board. Every plan item resolves to an
// "effective" date with a kind: published (posted_at) > scheduled (scheduled_at)
// > proposed (sequential slot = month start + position). Drives Kanban sorting,
// calendar placement, and the date badge so all three views stay consistent.

import { dayKey, formatDate, formatTime, toDate as parseDate } from "./format";

// Re-exported under the board's own names.
export { parseDate, dayKey };

/** First of the month the plan is anchored to (from plan.start_date). */
export function monthStartOf(plan) {
  const sd = parseDate(plan?.start_date);
  return sd ? new Date(sd.getFullYear(), sd.getMonth(), 1) : null;
}

/** The day the plan's first slot falls on. A plan that starts on the 8th
 * proposes its first post for the 8th; anchoring on the month start put a
 * week plan's proposed days a week early, before its own published ones. */
export function planStartOf(plan) {
  const sd = parseDate(plan?.start_date);
  return sd ? new Date(sd.getFullYear(), sd.getMonth(), sd.getDate()) : null;
}

function addDays(date, n) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

// Board copy is English, so the date badge is pinned to it too.
const fmtDate = (d) => formatDate(d, { withYear: false, locale: "en" });
const fmtTime = (d) => formatTime(d, { locale: "en" });

const KIND_LABEL = { published: "Published", scheduled: "Scheduled", proposed: "Planned" };

/**
 * Resolve an item's effective schedule.
 *   day      — the plan.days[] entry (status, etc.)
 *   post     — the linked full post (or null)
 *   anchor   — Date the plan's first slot falls on (planStartOf) or null
 *   index    — the item's position in days[] (for the proposed slot)
 * Returns { date, time|null, kind, label, status, hasTime }.
 */
export function effectiveSchedule(day, post, anchor, index) {
  const status = post?.status || day?.status || "pending";
  const posted = parseDate(post?.posted_at);
  const scheduled = parseDate(post?.scheduled_at);

  let date = null;
  let kind = "proposed";
  let hasTime = false;

  if (posted) {
    date = posted; kind = "published"; hasTime = true;
  } else if (scheduled) {
    date = scheduled; kind = "scheduled"; hasTime = true;
  } else if (anchor) {
    date = addDays(anchor, index || 0); kind = "proposed"; hasTime = false;
  }

  const dateLabel = date ? `${fmtDate(date)}${hasTime ? `, ${fmtTime(date)}` : ""}` : "";
  const label = date ? `${KIND_LABEL[kind]} ${dateLabel}` : KIND_LABEL[kind];

  return { date, time: hasTime ? fmtTime(date) : null, kind, label, dateLabel, status, hasTime };
}

