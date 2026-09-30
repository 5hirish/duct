import { beforeEach, describe, expect, it } from "vitest";
import {
  REMINDER_KEY,
  ReminderKind,
  isDue,
  localDay,
  readReminder,
  reminderFor,
  writeReminder,
} from "../dailyReminder.js";
import { absoluteTime, localPickerValue } from "../contentApi.js";

// 2026-10-01, a Thursday, at 09:30 on this machine's own clock.
const MORNING = new Date(2026, 9, 1, 9, 30);

describe("the daily reminder", () => {
  beforeEach(() => {
    const data = new Map();
    globalThis.window = {
      localStorage: {
        getItem: (k) => (data.has(k) ? data.get(k) : null),
        setItem: (k, v) => data.set(k, String(v)),
      },
    };
  });

  it("is due once a day, after its time, unless it is off", () => {
    expect(isDue({ time: "09:00", off: false, last: "" }, MORNING)).toBe(true);
    expect(isDue({ time: "10:00", off: false, last: "" }, MORNING)).toBe(false);
    expect(isDue({ time: "09:00", off: false, last: "2026-10-01" }, MORNING)).toBe(false);
    expect(isDue({ time: "09:00", off: true, last: "" }, MORNING)).toBe(false);
  });

  it("says drafts first, then asks for today's reflection, then nothing", () => {
    const queue = [{ drafts: [{ id: "a" }, { id: "b" }] }];
    expect(reminderFor({ queue, journal: [], now: MORNING })).toEqual({ kind: ReminderKind.DRAFTS, count: 2 });
    expect(reminderFor({ queue: [], journal: [], now: MORNING })).toEqual({ kind: ReminderKind.REFLECT, count: 0 });
    expect(reminderFor({ queue: [], journal: [{ day: "2026-10-01" }], now: MORNING })).toBeNull();
  });

  it("keeps its setting per device and survives a bad value", () => {
    writeReminder({ time: "08:00" });
    expect(readReminder()).toMatchObject({ time: "08:00", off: false });
    window.localStorage.setItem(REMINDER_KEY, "{not json");
    expect(readReminder().time).toBe("09:00");
  });

  it("names the day on the reader's own calendar", () => {
    expect(localDay(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });
});

describe("a schedule time", () => {
  it("goes to the server as the instant the reader picked, not as UTC", () => {
    const picked = new Date(2026, 9, 2, 9, 0);
    expect(localPickerValue(picked)).toBe("2026-10-02T09:00");
    expect(absoluteTime("2026-10-02T09:00")).toBe(picked.toISOString());
  });
});
