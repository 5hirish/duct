// A schedule time the picker shows in the reader's zone has to reach the
// server as the instant they meant. It once went without a zone and was read
// as UTC, so a post set for 9:00 in Madrid went out at 11:00 (CEST) and the
// picker's earliest time was two hours off too.
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { absoluteTime, localPickerValue } from "../contentApi.js";

const originalTz = process.env.TZ;

beforeAll(() => { process.env.TZ = "Europe/Madrid"; });
afterAll(() => { process.env.TZ = originalTz; });

describe("absoluteTime", () => {
  it("reads the picker's value as the reader's local time", () => {
    expect(absoluteTime("2026-10-02T09:00")).toBe("2026-10-02T07:00:00.000Z");   // CEST, +02:00
    expect(absoluteTime("2026-11-02T09:00")).toBe("2026-11-02T08:00:00.000Z");   // CET, +01:00
  });

  it("leaves nothing, and anything it cannot read, as it was", () => {
    expect(absoluteTime("")).toBe("");
    expect(absoluteTime(null)).toBe(null);
    expect(absoluteTime("next tuesday")).toBe("next tuesday");
  });
});

describe("localPickerValue", () => {
  it("shows an instant in the reader's zone, not in UTC", () => {
    expect(localPickerValue(new Date("2026-10-02T07:00:00Z"))).toBe("2026-10-02T09:00");
    expect(localPickerValue("2026-11-02T08:00:00Z")).toBe("2026-11-02T09:00");
  });

  it("round-trips with absoluteTime", () => {
    expect(absoluteTime(localPickerValue("2026-10-02T07:05:00Z"))).toBe("2026-10-02T07:05:00.000Z");
  });

  it("is empty for a time it cannot read", () => {
    expect(localPickerValue("not a date")).toBe("");
  });
});
