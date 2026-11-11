/**
 * Scheduled runs (#562): the values the Scheduled page reads, as codes and
 * facts. No words here; the components map them to message descriptors.
 * The backend's half is `service/schedules.py`; the values are its wire values.
 */

export const Cadence = Object.freeze({
  HOURLY: "hourly",
  DAILY: "daily",
  WEEKDAYS: "weekdays",
  WEEKLY: "weekly",
  // Checked hourly, run only when a release is published (#563).
  ON_RELEASE: "on_release",
  MANUAL: "manual",
});

export const JobKind = Object.freeze({ CONTENT_PLAN_FROM_WORK: "content.plan_from_work" });

export const Outcome = Object.freeze({
  PROPOSED: "proposed",
  NOTHING_NEW: "nothing_new",
  NO_PROPOSAL: "no_proposal",
  FAILED: "failed",
  SKIPPED: "skipped",
  INTERRUPTED: "interrupted",
});

/** What a schedule card leads with, in order of what the person must know. */
export const ScheduleState = Object.freeze({
  RUNNING: "running",
  NEEDS_YOU: "needs_you",
  WAITING_ON_YOU: "waiting_on_you",
  PAUSED: "paused",
  ACTIVE: "active",
});

export function scheduleState(s) {
  if (!s) return ScheduleState.ACTIVE;
  if (s.running) return ScheduleState.RUNNING;
  if (s.needs_reason) return ScheduleState.NEEDS_YOU;
  if (!s.enabled) return ScheduleState.PAUSED;
  // The server says whether the proposal is still unanswered; an older
  // response without the field falls back to the last outcome.
  if (typeof s.waiting === "boolean" ? s.waiting : s.last?.outcome === Outcome.PROPOSED) {
    return ScheduleState.WAITING_ON_YOU;
  }
  return ScheduleState.ACTIVE;
}

/** The person's zone, for a new schedule. UTC when the browser will not say. */
export function localTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** How many schedules have a proposal waiting: the sidebar's count. */
export function waitingCount(rows) {
  return (Array.isArray(rows) ? rows : []).filter((s) => s?.enabled && s?.waiting === true).length;
}

/**
 * A plan from shipped work on the setup sheet's answers, repeating: Mondays
 * at 09:00 local (the default), or whenever a release is published.
 */
export function feedScheduleBody(projectId, options, { timeZone = localTimeZone(), cadence = Cadence.WEEKLY } = {}) {
  const o = options || {};
  return {
    project_id: projectId,
    job: JobKind.CONTENT_PLAN_FROM_WORK,
    cadence: cadence === Cadence.ON_RELEASE ? Cadence.ON_RELEASE : Cadence.WEEKLY,
    weekday: 0,
    at_time: "09:00",
    timezone: timeZone,
    config: {
      feed: {
        sources: o.sources,
        max_days: o.maxDays,
        disclosure: o.disclosure,
        ...(o.lookBack ? { look_back_days: o.lookBack } : {}),
      },
      horizon: o.horizon || 7,
    },
  };
}

/** Where a run's conversation opens: the plan session, resumed. */
export function runConversationHref(conversationId) {
  return conversationId ? `/content/sessions/new?conversation=${encodeURIComponent(conversationId)}` : null;
}

/** The cost of a run as a short figure, or null when unpriced. */
export function runCost(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return null;
  const n = Number(value);
  if (n === 0) return "$0";
  return n < 0.01 ? "<$0.01" : `$${n.toFixed(2)}`;
}

// Stones in a card's run strip: the last runs, oldest first, then the next.
export const RUN_STRIP_SLOTS = 8;

/**
 * A card's run strip as codes: the last runs oldest first (the route sends
 * them newest first), padded with empty slots so every card's strip is the
 * same length, then one "next" stone while the schedule is on.
 */
export function runStrip(recent, { enabled = true, slots = RUN_STRIP_SLOTS } = {}) {
  const past = (Array.isArray(recent) ? recent : []).slice(0, slots).reverse()
    .map((r, i) => ({ key: `r-${r.at || i}`, outcome: r.outcome || "", at: r.at || null, retry: Boolean(r.will_retry) }));
  const pad = Array.from({ length: Math.max(0, slots - past.length) }, (_, i) => ({ key: `e-${i}`, outcome: "empty", at: null }));
  return [...pad, ...past, ...(enabled ? [{ key: "next", outcome: "next", at: null }] : [])];
}

/** The month's runs against its cap, as pips: used ones first. */
export function capPips(used, cap) {
  const n = Math.max(0, Number(cap) || 0);
  const u = Math.min(n, Math.max(0, Number(used) || 0));
  return Array.from({ length: n }, (_, i) => i < u);
}
