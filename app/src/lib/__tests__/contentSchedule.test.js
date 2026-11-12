import { describe, expect, it } from "vitest";
import { MAX_PLAN_DAYS, PlanLength, monthPeriod, nextPlanStart, planPeriodOptions, planStartOf, AgendaGroup, PlanState, agendaGroups, isMissed, planItems, orderPlans, planProgress, planState, PlanAction, planActions, planOutlook, nextOpenDay, planChanges } from "../contentSchedule";
import { planScenario, randomPlan } from "../__fixtures__/planScenarios.mjs";

// The same rules as backend/tests/test_content_plan_period.py: the buttons
// name dates the run will then plan, so the two must agree.

const day = (y, m, d) => new Date(y, m - 1, d);
const plan = (start, n) => ({ start_date: start, days: Array.from({ length: n }, () => ({})) });
const span = (o) => [o.length, o.start.getDate(), o.end.getMonth() + 1, o.end.getDate()];

describe("plan periods", () => {
  it("reads a plan's start as a calendar date, not UTC midnight", () => {
    expect(planStartOf(plan("2026-10-07", 1))).toEqual(day(2026, 10, 7));
  });

  it("plans the rest of the month, and rolls over in its last days", () => {
    expect(monthPeriod(day(2026, 10, 25))).toEqual({ start: day(2026, 10, 25), days: 7 });
    expect(monthPeriod(day(2026, 10, 26))).toEqual({ start: day(2026, 11, 1), days: 30 });
    expect(monthPeriod(day(2026, 10, 1)).days).toBe(MAX_PLAN_DAYS);
  });

  it("offers each length from the start", () => {
    expect(planPeriodOptions(day(2026, 10, 7)).map(span)).toEqual([
      [PlanLength.MONTH, 7, 10, 31],
      [PlanLength.WEEK, 7, 10, 13],
      [PlanLength.TWO_WEEKS, 7, 10, 20],
      [PlanLength.THIRTY_DAYS, 7, 11, 5],
    ]);
  });

  it("stops short of the next plan and offers the same dates once", () => {
    const options = planPeriodOptions(day(2026, 10, 7), [plan("2026-10-18", 7)]);
    expect(options.map(span)).toEqual([
      [PlanLength.MONTH, 7, 10, 17],
      [PlanLength.WEEK, 7, 10, 13],
    ]);
  });

  it("leaves out a rolled-over month that is already planned", () => {
    const options = planPeriodOptions(day(2026, 10, 28), [plan("2026-11-01", 30)]);
    expect(options.map((o) => o.length)).toEqual([PlanLength.WEEK]);
    expect(options[0].days).toBe(4);
  });

  it("plans ahead from the day after the last plan still running", () => {
    expect(nextPlanStart([plan("2026-10-07", 25)], day(2026, 10, 9))).toEqual(day(2026, 11, 1));
    expect(nextPlanStart([plan("2026-09-01", 30)], day(2026, 10, 9))).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// What today makes of a plan, over generated plans
// ---------------------------------------------------------------------------

describe("a plan read on a given day", () => {
  const today = new Date(2026, 10, 3); // Tuesday 3 November 2026

  it("knows a plan that ended, and counts what was missed", () => {
    const { plan, postsById } = planScenario("ended-nothing-posted", today);
    expect(planState(plan, today)).toBe(PlanState.ENDED);
    const progress = planProgress(planItems(plan, postsById, { today }));
    expect(progress).toMatchObject({ total: 30, posted: 0, missed: 30 });
    const groups = agendaGroups(planItems(plan, postsById, { today }), today);
    expect(groups.map((g) => g.kind)).toEqual([AgendaGroup.MISSED]);
  });

  it("puts today's and next week's posts under their weeks, ahead of the folded past", () => {
    const { plan, postsById } = planScenario("mid-month", today);
    expect(planState(plan, today)).toBe(PlanState.RUNNING);
    const kinds = agendaGroups(planItems(plan, postsById, { today }), today).map((g) => g.kind);
    expect(kinds[0]).toBe(AgendaGroup.MISSED);
    expect(kinds.at(-1)).toBe(AgendaGroup.EARLIER);
    expect(kinds.filter((k) => k === AgendaGroup.WEEK).length).toBeGreaterThan(1);
  });

  it("a plan made ahead is upcoming and has nothing missed", () => {
    const { plan } = planScenario("planned-ahead", today);
    expect(planState(plan, today)).toBe(PlanState.UPCOMING);
    expect(agendaGroups(planItems(plan, {}, { today }), today).every((g) => g.kind === AgendaGroup.WEEK)).toBe(true);
  });

  it("a draft whose day passed is late, not missed: it can still go out", () => {
    expect(isMissed("draft", new Date(2026, 10, 1), today)).toBe(false);
    expect(isMissed("pending", new Date(2026, 10, 1), today)).toBe(true);
    expect(isMissed("pending", today, today)).toBe(false);
  });

  it("over 500 random plans, every post lands in exactly one group, in order", () => {
    for (let seed = 1; seed <= 500; seed += 1) {
      const { plan, postsById } = randomPlan(seed, today);
      const items = planItems(plan, postsById, { today });
      const groups = agendaGroups(items, today);
      const placed = groups.flatMap((g) => g.items.map((it) => it.index));
      expect(placed.sort((a, b) => a - b)).toEqual(items.map((it) => it.index).sort((a, b) => a - b));
      const order = groups.map((g) => (g.kind === AgendaGroup.MISSED ? -1 : g.kind === AgendaGroup.WEEK ? g.offset : 1e6));
      expect(order).toEqual([...order].sort((a, b) => a - b));
      for (const g of groups) {
        if (g.kind === AgendaGroup.MISSED) expect(g.items.every((it) => it.status === "pending" && it.schedule.date < today)).toBe(true);
        if (g.kind === AgendaGroup.WEEK) expect(g.offset).toBeGreaterThanOrEqual(0);
      }
      const p = planProgress(items);
      expect(p.posted + p.missed + p.pending + p.drafted).toBe(p.total);
    }
  });
});

describe("orderPlans", () => {
  const today = new Date(2026, 10, 9);
  const plan = (id, start) => ({ id, start_date: start, days: Array.from({ length: 7 }, () => ({})) });

  it("puts today's plan first, then what is ahead, then what ended", () => {
    const plans = [
      plan("sep", "2026-09-01"),
      plan("dec", "2026-12-01"),
      plan("nov", "2026-11-06"),
      plan("oct", "2026-10-01"),
      plan("nov-late", "2026-11-20"),
      plan("undated", null),
    ];
    expect(orderPlans(plans, today).map((p) => p.id)).toEqual(["nov", "nov-late", "dec", "undated", "oct", "sep"]);
  });
});

describe("planActions", () => {
  const today = new Date(2026, 10, 9);
  const plan = (start, statuses) => ({ id: "p", start_date: start, days: statuses.map((status) => ({ status })) });

  it("offers a revision while a day ahead waits, and a catch-up for days missed", () => {
    // Nov 6–12: the 6th and 8th passed undrafted, the 7th was drafted.
    const running = plan("2026-11-06", ["pending", "draft", "pending", "pending", "pending", "posted", "pending"]);
    expect(planOutlook(running, today)).toMatchObject({ missed: 2, open: 3 });
    expect(planActions(running, today)).toEqual([{ id: PlanAction.REVISE }, { id: PlanAction.CATCH_UP, missed: 2 }]);
  });

  it("offers nothing once the plan has ended or every day ahead is drafted", () => {
    expect(planActions(plan("2026-10-01", ["pending", "pending"]), today)).toEqual([]);
    expect(planActions(plan("2026-11-08", ["pending", "draft", "posted"]), today)).toEqual([]);
    expect(planActions(null, today)).toEqual([]);
  });

  it("names the first day from today on still waiting for a draft", () => {
    const running = plan("2026-11-06", ["pending", "draft", "pending", "draft", "pending"]);
    expect(nextOpenDay(running, today)?.index).toBe(4);
    expect(nextOpenDay(plan("2026-11-06", ["pending", "draft", "posted", "draft"]), today)).toBe(null);
  });

  it("offers only a revision for a plan that has not started", () => {
    expect(planActions(plan("2026-12-01", ["pending", "pending"]), today)).toEqual([{ id: PlanAction.REVISE }]);
  });
});

describe("planChanges", () => {
  it("reads a change to some days as each day before and after, with the fields that moved", () => {
    const plan = {
      start_date: "2026-11-01",
      days: [{ topic: "a" }, { topic: "b" }, { topic: "Capsule in 5 pieces", post_type: "image", platforms: ["tiktok"] }],
      only_days: true,
      changed_days: [2],
      previous_days: [{ topic: "c", post_type: "slideshow", platforms: ["tiktok"] }],
    };
    const [change] = planChanges(plan);
    expect(change.index).toBe(2);
    expect(change.date).toEqual(new Date(2026, 10, 3));
    expect(change.before.topic).toBe("c");
    expect(change.fields).toEqual(["topic", "post_type"]);
  });

  it("is empty for a whole plan", () => {
    expect(planChanges({ start_date: "2026-11-01", days: [{ topic: "a" }] })).toEqual([]);
    expect(planChanges(null)).toEqual([]);
  });
});
