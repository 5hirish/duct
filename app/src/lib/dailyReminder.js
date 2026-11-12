"use client";

// The one notice a day the drafts queue sends (issue #266): "3 drafts ready".
// A posting habit lives or dies on cadence, and a queue nobody remembers to
// open is drafts that go stale where they were written.
//
// Per device, in localStorage, because the notice is: it comes from the
// desktop shell's notification plugin (or a browser tab that was granted
// one), and a phone that never runs the app has nothing to say it on. The
// time and the switch live with it for the same reason.
//
// The words come from the caller: this module decides *whether* and *how
// many*, never the sentence, so it stays plain functions a test can run.

export const REMINDER_KEY = "duct_daily_drafts_reminder";
export const DEFAULT_TIME = "09:00";
/** How often an open app looks at the clock. A notice is due to the minute, not the second. */
export const REMINDER_INTERVAL_MS = 10 * 60 * 1000;
/** The times the setting offers, besides off. */
export const REMINDER_TIMES = ["07:00", "08:00", "09:00", "10:00", "12:00", "17:00", "19:00"];

const DEFAULTS = Object.freeze({ time: DEFAULT_TIME, off: false, last: "" });

function store() {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    // Private mode / storage disabled: the notice keeps its defaults.
    return null;
  }
}

export function readReminder() {
  try {
    const raw = store()?.getItem(REMINDER_KEY);
    return { ...DEFAULTS, ...(raw ? JSON.parse(raw) : {}) };
  } catch {
    // A value from an older build, or hand-edited: start over at the default.
    return { ...DEFAULTS };
  }
}

export function writeReminder(patch) {
  const next = { ...readReminder(), ...patch };
  try {
    store()?.setItem(REMINDER_KEY, JSON.stringify(next));
  } catch {
    // Quota or disabled storage: the choice lasts this page load.
  }
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
 * How many drafts today's notice should name, or null when it owes none: a
 * day with nothing waiting is not worth interrupting anyone for, and no
 * "time to write" nudge stands in, because a notice that nags trains people
 * to switch it off.
 */
export function reminderFor(drafts) {
  const count = Array.isArray(drafts) ? drafts.length : 0;
  return count > 0 ? { count } : null;
}
