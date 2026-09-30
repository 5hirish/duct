"use client";

// The one notice a day the drafts queue sends (issue #266): "3 drafts ready",
// or, before today's reflection exists, a nudge to write it. A build-in-public
// habit lives or dies on cadence, and a queue nobody remembers to open is the
// failure the Cowork job it replaces had.
//
// Per device, in localStorage, because the notice is: it comes from the
// desktop shell's notification plugin (or a browser tab that was granted
// one), and a phone that never runs the app has nothing to say it on. The
// time and the switch live with it for the same reason.
//
// The words come from the caller: this module decides *whether* and *what
// kind*, never the sentence, so it stays plain functions a test can run.

export const REMINDER_KEY = "duct.dailyReflectionReminder";
export const DEFAULT_TIME = "09:00";
/** How often an open app looks at the clock. A notice is due to the minute, not the second. */
export const REMINDER_INTERVAL_MS = 10 * 60 * 1000;
/** The times the setting offers, besides off. */
export const REMINDER_TIMES = ["07:00", "08:00", "09:00", "10:00", "12:00", "17:00", "19:00"];

export const ReminderKind = Object.freeze({
  DRAFTS: "drafts",     // drafts are waiting
  REFLECT: "reflect",   // today has no reflection yet
});

function store() {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

export function readReminder() {
  const raw = store()?.getItem(REMINDER_KEY);
  try {
    const parsed = raw ? JSON.parse(raw) : {};
    return { time: DEFAULT_TIME, off: false, last: "", ...parsed };
  } catch {
    return { time: DEFAULT_TIME, off: false, last: "" };
  }
}

export function writeReminder(patch) {
  const next = { ...readReminder(), ...patch };
  store()?.setItem(REMINDER_KEY, JSON.stringify(next));
  return next;
}

/** "YYYY-MM-DD" on the reader's own calendar. */
export function localDay(now) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Whether today's notice is owed: on, not already sent today, and past its time. */
export function isDue(settings, now) {
  if (settings.off) return false;
  if (settings.last === localDay(now)) return false;
  const [h, m] = String(settings.time || DEFAULT_TIME).split(":").map(Number);
  return now.getHours() * 60 + now.getMinutes() >= h * 60 + (m || 0);
}

/**
 * What today's notice should say, from the queue and the journal: waiting
 * drafts first (the queue is the point), then a nudge when today has no
 * reflection at all, else nothing — a day already reflected on and answered
 * owes no notice.
 */
export function reminderFor({ queue, journal, now }) {
  const waiting = (queue || []).reduce((n, d) => n + (d.drafts?.length || 0), 0);
  if (waiting > 0) return { kind: ReminderKind.DRAFTS, count: waiting };
  const today = localDay(now);
  if (!(journal || []).some((r) => r.day === today)) return { kind: ReminderKind.REFLECT, count: 0 };
  return null;
}
