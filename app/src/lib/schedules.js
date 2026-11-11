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
  if (s.last?.outcome === Outcome.PROPOSED) return ScheduleState.WAITING_ON_YOU;
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

/** A weekly plan from shipped work with the setup sheet's answers: Mondays at 09:00 local. */
export function feedScheduleBody(projectId, options, { timeZone = localTimeZone() } = {}) {
  const o = options || {};
  return {
    project_id: projectId,
    job: JobKind.CONTENT_PLAN_FROM_WORK,
    cadence: Cadence.WEEKLY,
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
