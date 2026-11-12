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
 *   today    — the reader's today (start of day), for `missed`; tests pass one
 * Returns { date, time|null, kind, kindLabel, dateLabel, status, hasTime,
 * missed }; `kindLabel` is a message descriptor.
 */
export function effectiveSchedule(day, post, anchor, index, { locale, today = startOfDay(new Date()) } = {}) {
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

  return {
    date, time: hasTime ? fmtTime(date) : null, kind, kindLabel: KIND_LABEL[kind], dateLabel, status, hasTime,
    missed: isMissed(status, date, today),
  };
}

// ---------------------------------------------------------------------------
// Time: what a plan is, today
// ---------------------------------------------------------------------------
//
// A plan is written for dates, and the board used to show it the same way
// whatever today was: a person back on 3 November saw October's thirty posts
// still "Pending", none of them drafted, as if the month were ahead of them.
// These answer what the dates mean now, so every view says it the same way.

export function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/**
 * A planned post whose day has passed without a draft. Pending only: a draft
 * whose slot passed can still be approved and sent late, and a scheduled or
 * posted one already went somewhere.
 */
export function isMissed(status, date, today = startOfDay(new Date())) {
  return status === "pending" && Boolean(date) && date < today;
}

export const PlanState = Object.freeze({ UPCOMING: "upcoming", RUNNING: "running", ENDED: "ended" });

/** Whether a plan's dates are ahead, under way, or behind `today`. */
export function planState(plan, today = startOfDay(new Date())) {
  const start = planStartOf(plan);
  const end = planEndOf(plan);
  if (!start || !end) return PlanState.UPCOMING;
  if (today < start) return PlanState.UPCOMING;
  if (today > end) return PlanState.ENDED;
  return PlanState.RUNNING;
}

const STATE_RANK = { [PlanState.RUNNING]: 0, [PlanState.UPCOMING]: 1, [PlanState.ENDED]: 2 };

/**
 * The plan picker's order: the plan running today first, then the ones ahead,
 * soonest first, then the ones that ended, latest first. A plan with no date
 * reads as ahead and goes last among them.
 */
export function orderPlans(plans, today = startOfDay(new Date())) {
  const keyed = (Array.isArray(plans) ? plans : []).map((plan) => ({
    plan,
    state: planState(plan, today),
    start: planStartOf(plan)?.getTime() ?? Infinity,
  }));
  keyed.sort((a, b) => {
    const byState = STATE_RANK[a.state] - STATE_RANK[b.state];
    if (byState) return byState;
    if (a.start === b.start) return 0;
    return a.state === PlanState.ENDED ? b.start - a.start : a.start - b.start;
  });
  return keyed.map((k) => k.plan);
}

/**
 * Every day of a plan with its effective schedule, in date order, the plan's
 * own order breaking ties and undated days last. The one place the views get
 * their rows from, so the agenda, the board and the counts cannot disagree.
 */
export function planItems(plan, postsById = {}, { locale, today = startOfDay(new Date()) } = {}) {
  const start = planStartOf(plan);
  const days = Array.isArray(plan?.days) ? plan.days : [];
  const rows = days.map((day, index) => {
    const post = day?.post_id ? postsById[day.post_id] || null : null;
    const schedule = effectiveSchedule(day, post, start, index, { locale, today });
    return { day, post, schedule, index, status: schedule.status || "pending" };
  });
  rows.sort((a, b) => {
    const ta = a.schedule.date?.getTime() ?? Infinity;
    const tb = b.schedule.date?.getTime() ?? Infinity;
    return ta - tb || a.index - b.index;
  });
  return rows;
}

/** The platforms a plan day posts to: the saved post's once there is one, the day's before. */
export function dayPlatforms(day, post) {
  const list = Array.isArray(post?.platforms) && post.platforms.length ? post.platforms : day?.platforms;
  return Array.isArray(list) ? list.filter(Boolean) : [];
}

/** True when the item is on `channel` (or when no channel is asked for). */
export function onChannel(item, channel) {
  return !channel || dayPlatforms(item.day, item.post).includes(channel);
}

/** The channels a plan's days are on, most used first: [{ channel, count }]. */
export function planChannels(items) {
  const counts = new Map();
  for (const it of items) for (const c of dayPlatforms(it.day, it.post)) counts.set(c, (counts.get(c) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([channel, count]) => ({ channel, count }));
}

/** The counts a plan's header says: how much went out, how much was missed. */
export function planProgress(items) {
  const out = { total: items.length, posted: 0, drafted: 0, missed: 0, pending: 0 };
  for (const it of items) {
    if (it.status === "posted") out.posted += 1;
    else if (it.schedule.missed) out.missed += 1;
    else if (it.status === "pending") out.pending += 1;
    else out.drafted += 1;
  }
  return out;
}

/**
 * What is left to act on in a plan, as of `today`: the days that passed with
 * nothing drafted (`missed`) and the days from today on still waiting for a
 * draft (`open`), the ones a revision can still change. Drafted and posted
 * days count for neither: a revision keeps them.
 */
export function planOutlook(plan, today = startOfDay(new Date())) {
  const out = { state: planState(plan, today), missed: 0, open: 0 };
  for (const it of planItems(plan, {}, { today })) {
    if (it.schedule.missed) out.missed += 1;
    else if (it.status === "pending" && it.schedule.date && it.schedule.date >= today) out.open += 1;
  }
  return out;
}

/** The first day from `today` on still waiting for a draft: { day, index } as planItems has it, or null. */
export function nextOpenDay(plan, today = startOfDay(new Date())) {
  return (
    planItems(plan, {}, { today }).find(
      (it) => it.status === "pending" && it.schedule.date && it.schedule.date >= today
    ) || null
  );
}

/**
 * The fields a change to some days can move, in the order a reader scans a
 * day: what it is about first, then where and how it posts, then its bets.
 */
export const CHANGE_FIELDS = Object.freeze([
  "topic", "post_type", "platforms", "pillar", "hook_type", "hook_emotion",
  "funnel_stage", "objective", "series", "experiment", "format_slug",
]);

const sameValue = (a, b) => JSON.stringify(a ?? "") === JSON.stringify(b ?? "");

/**
 * A proposal that changes some days of a plan (`only_days`), day by day:
 * `{ index, date, before, after, fields }`, where `fields` are the
 * CHANGE_FIELDS that moved. The backend sends the changed indexes and what
 * each day said before (`changed_days`, `previous_days`), so the pane shows
 * the change rather than thirty days to compare by eye.
 */
export function planChanges(plan) {
  const indexes = Array.isArray(plan?.changed_days) ? plan.changed_days : [];
  const previous = Array.isArray(plan?.previous_days) ? plan.previous_days : [];
  const days = Array.isArray(plan?.days) ? plan.days : [];
  const start = planStartOf(plan);
  return indexes.map((index, k) => {
    const before = previous[k] || {};
    const after = days[index] || {};
    return {
      index,
      date: start ? addDays(start, index) : null,
      before,
      after,
      fields: CHANGE_FIELDS.filter((f) => !sameValue(before[f], after[f])),
    };
  });
}

/** The next steps a plan session offers over its composer. */
export const PlanAction = Object.freeze({ REVISE: "revise", CATCH_UP: "catch_up" });

/**
 * Which of them a plan offers, from its dates and days alone, so they are
 * instant and always true: revise what is left while a day ahead still waits
 * for a draft, and catch up when days passed with nothing drafted and there
 * are days ahead to fit them into. Nothing for an ended plan.
 */
export function planActions(plan, today = startOfDay(new Date())) {
  if (!plan || !Array.isArray(plan.days) || plan.days.length === 0) return [];
  const { state, missed, open } = planOutlook(plan, today);
  if (state === PlanState.ENDED || open === 0) return [];
  const actions = [{ id: PlanAction.REVISE }];
  if (missed > 0) actions.push({ id: PlanAction.CATCH_UP, missed });
  return actions;
}

export const AgendaGroup = Object.freeze({ MISSED: "missed", WEEK: "week", EARLIER: "earlier", UNDATED: "undated" });

// Weeks start on Monday, the ISO week, so "this week" does not change meaning
// on a Sunday.
function weekStart(date) {
  const d = startOfDay(date);
  return addDays(d, -((d.getDay() + 6) % 7));
}

function weeksBetween(from, to) {
  const utc = (d) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.floor((utc(to) - utc(from)) / (7 * 86_400_000));
}

/**
 * The agenda: a plan's rows grouped by what today makes of them.
 *
 *   missed   — planned, never drafted, day passed: the actionable past, first
 *   week     — this week and every week after, `offset` 0, 1, 2…
 *   earlier  — the rest of the past (posted, or drafted late), folded away
 *   undated  — no date at all, last
 *
 * Every row lands in exactly one group, and the groups come back in that
 * order, weeks ascending. Pure, so it is asserted on over generated plans.
 */
export function agendaGroups(items, today = startOfDay(new Date())) {
  const thisWeek = weekStart(today);
  const missed = [];
  const earlier = [];
  const undated = [];
  const weeks = new Map();
  for (const it of items) {
    const date = it.schedule.date;
    if (!date) undated.push(it);
    else if (it.schedule.missed) missed.push(it);
    else if (date < thisWeek) earlier.push(it);
    else {
      const offset = weeksBetween(thisWeek, date);
      if (!weeks.has(offset)) weeks.set(offset, []);
      weeks.get(offset).push(it);
    }
  }
  const groups = [];
  if (missed.length) groups.push({ key: "missed", kind: AgendaGroup.MISSED, items: missed });
  for (const offset of [...weeks.keys()].sort((a, b) => a - b)) {
    const from = addDays(thisWeek, offset * 7);
    groups.push({ key: `week-${offset}`, kind: AgendaGroup.WEEK, offset, from, to: addDays(from, 6), items: weeks.get(offset) });
  }
  if (earlier.length) groups.push({ key: "earlier", kind: AgendaGroup.EARLIER, items: earlier });
  if (undated.length) groups.push({ key: "undated", kind: AgendaGroup.UNDATED, items: undated });
  return groups;
}

