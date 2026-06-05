"use client";

// Shared date model for the plan board. Every plan item resolves to an
// "effective" date with a kind: published (posted_at) > scheduled (scheduled_at)
// > proposed (sequential slot = month start + position). Drives Kanban sorting,
// calendar placement, and the date badge so all three views stay consistent.

export function parseDate(s) {
  if (!s) return null;
  const d = s instanceof Date ? s : new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** First of the month the plan is anchored to (from plan.start_date). */
export function monthStartOf(plan) {
  const sd = parseDate(plan?.start_date);
  return sd ? new Date(sd.getFullYear(), sd.getMonth(), 1) : null;
}

function addDays(date, n) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

function fmtDate(d) {
  return d.toLocaleDateString("en", { month: "short", day: "numeric" });
}
function fmtTime(d) {
  return d.toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" });
}

const KIND_LABEL = { published: "Published", scheduled: "Scheduled", proposed: "Planned" };

/**
 * Resolve an item's effective schedule.
 *   day      — the plan.days[] entry (status, etc.)
 *   post     — the linked full post (or null)
 *   monthStart — Date (first of the plan's month) or null
 *   index    — the item's position in days[] (for the proposed slot)
 * Returns { date, time|null, kind, label, status, hasTime }.
 */
export function effectiveSchedule(day, post, monthStart, index) {
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
  } else if (monthStart) {
    date = addDays(monthStart, index || 0); kind = "proposed"; hasTime = false;
  }

  const label = date
    ? `${KIND_LABEL[kind]} ${fmtDate(date)}${hasTime ? `, ${fmtTime(date)}` : ""}`
    : KIND_LABEL[kind];

  return { date, time: hasTime ? fmtTime(date) : null, kind, label, status, hasTime };
}

/** Stable YYYY-MM-DD key in local time. */
export function dayKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
