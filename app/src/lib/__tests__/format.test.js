import { describe, expect, it } from "vitest";
import { formatDateRange, formatDelta, formatElapsed, formatMeasure } from "../format";

describe("formatElapsed", () => {
  it("reads like a clock at every scale", () => {
    expect(formatElapsed(0)).toBe("0s");
    expect(formatElapsed(42)).toBe("42s");
    expect(formatElapsed(65)).toBe("1m 05s");
    expect(formatElapsed(3720)).toBe("1h 02m");
  });

  it("never counts backwards or from nothing", () => {
    expect(formatElapsed(-3)).toBe("0s");
    expect(formatElapsed(undefined)).toBe("0s");
  });
});

describe("a number an agent stored, with its unit", () => {
  it("reads every shape the unit can take", () => {
    expect(formatMeasure(0.112, "%", { locale: "en" })).toBe("11.2%");
    expect(formatMeasure(11.2, "%", { locale: "en" })).toBe("11.2%");
    expect(formatMeasure(2140, "EUR", { locale: "en" })).toBe("€2.1K");
    expect(formatMeasure(1840, "clicks", { locale: "en" })).toBe("1.8K clicks");
    expect(formatMeasure(71, "", { locale: "en" })).toBe("71");
    expect(formatMeasure("n/a", "USD")).toBe("");
  });

  it("signs a change, and says no change plainly", () => {
    expect(formatDelta(0.14, { locale: "en" })).toBe("+14%");
    expect(formatDelta(-0.091, { locale: "en" })).toBe("-9.1%");
    expect(formatDelta(0, { locale: "en" })).toBe("0%");
  });
});

describe("a span of days", () => {
  // The server (Node) and the browser must print the same characters, or
  // React discards the server's HTML as a hydration mismatch.
  it("uses plain spaces around the dash, whatever the ICU", () => {
    const span = formatDateRange(new Date(2026, 9, 27), new Date(2026, 10, 25), { locale: "en" });
    expect(span).toBe("Oct 27 – Nov 25");
    expect(span).not.toMatch(/[\u2009\u202f]/);
  });
});
