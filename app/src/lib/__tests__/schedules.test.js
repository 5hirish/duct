import { describe, expect, it } from "vitest";
import { ScheduleState, feedScheduleBody, runConversationHref, runCost, scheduleState } from "../schedules.js";

describe("what a schedule card leads with", () => {
  it("puts a running or blocked schedule ahead of everything else", () => {
    expect(scheduleState({ running: true, needs_reason: "no_model_key", enabled: false })).toBe(ScheduleState.RUNNING);
    expect(scheduleState({ needs_reason: "no_model_key", enabled: true })).toBe(ScheduleState.NEEDS_YOU);
    expect(scheduleState({ enabled: false, last: { outcome: "proposed" } })).toBe(ScheduleState.PAUSED);
    expect(scheduleState({ enabled: true, last: { outcome: "proposed" } })).toBe(ScheduleState.WAITING_ON_YOU);
    expect(scheduleState({ enabled: true, last: { outcome: "nothing_new" } })).toBe(ScheduleState.ACTIVE);
  });
});

describe("a weekly plan from shipped work", () => {
  it("carries the setup sheet's answers in the backend's shape", () => {
    const body = feedScheduleBody("p1", { sources: ["github"], maxDays: 3, disclosure: "releases", lookBack: 14, horizon: 14 },
      { timeZone: "Europe/Berlin" });
    expect(body).toEqual({
      project_id: "p1", job: "content.plan_from_work", cadence: "weekly", weekday: 0, at_time: "09:00",
      timezone: "Europe/Berlin",
      config: { feed: { sources: ["github"], max_days: 3, disclosure: "releases", look_back_days: 14 }, horizon: 14 },
    });
  });
});

describe("a run's figures", () => {
  it("opens its conversation and prices what was spent", () => {
    expect(runConversationHref("c-1")).toBe("/content/sessions/new?conversation=c-1");
    expect(runConversationHref(null)).toBe(null);
    expect(runCost(0.0995)).toBe("$0.10");
    expect(runCost(0)).toBe("$0");
    expect(runCost(0.004)).toBe("<$0.01");
    expect(runCost(null)).toBe(null);
  });
});

describe("the card's run strip", () => {
  it("is the last runs oldest first, padded to one length, then the next run", async () => {
    const { runStrip, RUN_STRIP_SLOTS } = await import("../schedules.js");
    const strip = runStrip([{ at: "2", outcome: "proposed" }, { at: "1", outcome: "failed" }]);
    expect(strip).toHaveLength(RUN_STRIP_SLOTS + 1);
    expect(strip.slice(-3).map((s) => s.outcome)).toEqual(["failed", "proposed", "next"]);
    expect(runStrip([], { enabled: false }).every((s) => s.outcome === "empty")).toBe(true);
  });

  it("counts the month's runs against the cap", async () => {
    const { capPips } = await import("../schedules.js");
    expect(capPips(2, 4)).toEqual([true, true, false, false]);
    expect(capPips(9, 3)).toEqual([true, true, true]);
  });
});

describe("on release, and what waits", () => {
  it("saves an on-release schedule and counts only proposals still unanswered", async () => {
    const { Cadence, feedScheduleBody, waitingCount, scheduleState, ScheduleState } = await import("../schedules.js");
    expect(feedScheduleBody("p", { sources: ["github"] }, { cadence: Cadence.ON_RELEASE }).cadence).toBe("on_release");
    expect(feedScheduleBody("p", {}, { cadence: "nonsense" }).cadence).toBe("weekly");
    const rows = [
      { enabled: true, waiting: true },
      { enabled: true, waiting: false, last: { outcome: "proposed" } },
      { enabled: false, waiting: true },
    ];
    expect(waitingCount(rows)).toBe(1);
    expect(scheduleState(rows[1])).toBe(ScheduleState.ACTIVE);
    expect(scheduleState({ enabled: true, last: { outcome: "proposed" } })).toBe(ScheduleState.WAITING_ON_YOU);
  });
});
