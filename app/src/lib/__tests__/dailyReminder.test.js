import { beforeEach, describe, expect, it } from "vitest";
import {
  REMINDER_KEY,
  isDue,
  localDay,
  readReminder,
  reminderFor,
  writeReminder,
} from "../dailyReminder.js";

// 2026-10-01, a Thursday, at 09:30 on this machine's own clock.
const MORNING = new Date(2026, 9, 1, 9, 30);

describe("the daily drafts reminder", () => {
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

  it("names the drafts waiting, and says nothing when none are", () => {
    expect(reminderFor([{ id: "a" }, { id: "b" }])).toEqual({ count: 2 });
    expect(reminderFor([])).toBeNull();
    expect(reminderFor(undefined)).toBeNull();
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
