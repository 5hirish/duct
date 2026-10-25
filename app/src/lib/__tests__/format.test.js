import { describe, expect, it } from "vitest";
import { formatElapsed } from "../format";

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
