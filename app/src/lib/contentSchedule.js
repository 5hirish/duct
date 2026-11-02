"use client";

// Shared date model for the plan board. Every plan item resolves to an
// "effective" date with a kind: published (posted_at) > scheduled (scheduled_at)
// > proposed (sequential slot = month start + position). Drives Kanban sorting,
// calendar placement, and the date badge so all three views stay consistent.

import { msg } from "@lingui/core/macro";
import { dayKey, formatDate, formatTime, toDate as parseDate } from "./format";

// Re-exported under the board's own names.
export { parseDate, dayKey };

// A plan's start_date is a calendar date ("2026-10-07"). `new Date()` reads
// that as UTC midnight, which is the evening before anywhere west of
// Greenwich, and every date on the plan moved back a day with it.
function calendarDate(value) {
  const ymd = typeof value === "string" && /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (ymd) return new Date(Number(ymd[1]), Number(ymd[2]) - 1, Number(ymd[3]));
  const d = parseDate(value);
  return d ? new Date(d.getFullYear(), d.getMonth(), d.getDate()) : null;
}

/** First of the month the plan is anchored to (from plan.start_date). */
export function monthStartOf(plan) {
  const sd = calendarDate(plan?.start_date);
  return sd ? new Date(sd.getFullYear(), sd.getMonth(), 1) : null;
}

/** The day the plan's first slot falls on. A plan that starts on the 8th
 * proposes its first post for the 8th; anchoring on the month start put a
 * week plan's proposed days a week early, before its own published ones. */
export function planStartOf(plan) {
  return calendarDate(plan?.start_date);
}

function addDays(date, n) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

/**
 * The period a plan manages: one post per date from its first day. The
 * backend holds the same rule (agents/content/plan_period.py) — a revision
 * keeps the dates, and a run opened while a plan covers a date manages that
 * plan rather than making a second one.
 */
export function planEndOf(plan) {
  const start = planStartOf(plan);
  const n = Array.isArray(plan?.days) ? plan.days.length : 0;
  return start && n > 0 ? addDays(start, n - 1) : null;
}

/** The plan covering `day` (a Date), newest first, or null. */
export function planCovering(plans, day) {
  const d = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  return (plans || []).find((p) => {
    const start = planStartOf(p);
    const end = planEndOf(p);
    return start && end && start <= d && d <= end;
  }) || null;
}

// The period rules of agents/content/plan_period.py, mirrored so a button can
// name its dates before the run starts: at most MAX_PLAN_DAYS, and a month
// with less than ROLLOVER_DAYS left is planned from the next month.
export const MAX_PLAN_DAYS = 30;
export const ROLLOVER_DAYS = 7;

// How far ahead a plan looks. MONTH is the month in progress, the default;
// the others are a number of days from the plan's first date.
export const PlanLength = Object.freeze({
  MONTH: "month",
  WEEK: "week",
  TWO_WEEKS: "two_weeks",
  THIRTY_DAYS: "thirty_days",
});
const LENGTH_DAYS = Object.freeze({
  [PlanLength.WEEK]: 7,
  [PlanLength.TWO_WEEKS]: 14,
  [PlanLength.THIRTY_DAYS]: MAX_PLAN_DAYS,
});

// Calendar days from a to b. Through UTC, because a local-time difference
// is an hour short across a daylight-saving change.
function daysBetween(a, b) {
  return Math.round(
    (Date.UTC(b.getFullYear(), b.getMonth(), b.getDate()) - Date.UTC(a.getFullYear(), a.getMonth(), a.getDate()))
      / 86_400_000,
  );
}

/** The rest of `start`'s month, or the whole of the next one when less than
 * ROLLOVER_DAYS are left. plan_period.month_period. */
export function monthPeriod(start) {
  let from = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  let monthEnd = new Date(from.getFullYear(), from.getMonth() + 1, 0);
  if (daysBetween(from, monthEnd) + 1 < ROLLOVER_DAYS) {
    from = addDays(monthEnd, 1);
    monthEnd = new Date(from.getFullYear(), from.getMonth() + 1, 0);
  }
  return { start: from, days: Math.min(daysBetween(from, monthEnd) + 1, MAX_PLAN_DAYS) };
}

/**
 * The periods a new plan from `from` can cover, one per PlanLength, as
 * `{ length, start, end, days, clipped }`. Each stops short of the next plan
 * already made (two plans never claim one date, the runner's
 * _resolve_plan_period; `clipped` says it did),
 * a month that rolled over into a planned month is left out, and lengths
 * that come to the same dates are offered once.
 */
export function planPeriodOptions(from, plans = []) {
  const options = [];
  for (const length of Object.values(PlanLength)) {
    const { start, days: wanted } = length === PlanLength.MONTH
      ? monthPeriod(from)
      : { start: new Date(from.getFullYear(), from.getMonth(), from.getDate()), days: LENGTH_DAYS[length] };
    if (planCovering(plans, start)) continue;
    const nextStart = (plans || [])
      .map(planStartOf)
      .filter((d) => d && d > start)
      .sort((a, b) => a - b)[0];
    const days = nextStart ? Math.min(wanted, daysBetween(start, nextStart)) : wanted;
    if (options.some((o) => o.start.getTime() === start.getTime() && o.days === days)) continue;
    options.push({ length, start, end: addDays(start, days - 1), days, clipped: days < wanted });
  }
  return options;
}

/** The day after the last plan ends, when that plan is still running or
 * ahead: where planning ahead starts. Null when nothing is planned past today. */
export function nextPlanStart(plans, today = new Date()) {
  const ends = (plans || []).map(planEndOf).filter(Boolean);
  if (ends.length === 0) return null;
  const last = new Date(Math.max(...ends));
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return last >= day ? addDays(last, 1) : null;
}

// Message descriptors (module-level table): render with `i18n._(KIND_LABEL[kind])`.
export const KIND_LABEL = Object.freeze({
  published: msg`Published`,
  scheduled: msg`Scheduled`,
  proposed: msg`Planned`,
});

/**
 * Resolve an item's effective schedule.
 *   day      — the plan.days[] entry (status, etc.)
 *   post     — the linked full post (or null)
 *   anchor   — Date the plan's first slot falls on (planStartOf) or null
 *   index    — the item's position in days[] (for the proposed slot)
 *   locale   — the interface language, so the date badge matches the copy
 *              around it (it used to be pinned to English, as the board was)
 * Returns { date, time|null, kind, kindLabel, dateLabel, status, hasTime };
 * `kindLabel` is a message descriptor.
 */
export function effectiveSchedule(day, post, anchor, index, { locale } = {}) {
  const fmtDate = (d) => formatDate(d, { withYear: false, locale });
  const fmtTime = (d) => formatTime(d, { locale });
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

  return { date, time: hasTime ? fmtTime(date) : null, kind, kindLabel: KIND_LABEL[kind], dateLabel, status, hasTime };
}

