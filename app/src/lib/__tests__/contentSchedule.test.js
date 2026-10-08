import { describe, expect, it } from "vitest";
import {
  MAX_PLAN_DAYS,
  PlanLength,
  monthPeriod,
  nextPlanStart,
  planPeriodOptions,
  planStartOf,
} from "../contentSchedule";

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
