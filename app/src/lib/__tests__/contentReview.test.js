import { describe, expect, it } from "vitest";

import { failedChecks, isScored, slideNumber, weakestMarkers } from "../contentReview";

const assessment = {
  overall: 64,
  checks: [
    { id: "slides_have_images", passed: true, severity: "hard", offenders: [] },
    { id: "hashtags_unique", passed: false, severity: "soft", offenders: ["#a"] },
    { id: "caption_present", passed: false, severity: "hard", offenders: [] },
  ],
  markers: [
    { id: "hook_strength", score: 55 },
    { id: "narrative_momentum", score: 80 },
    { id: "save_worthiness", score: 55 },
    { id: "visual_quality", score: 40 },
  ],
};

describe("contentReview", () => {
  it("puts what would ship broken before what would ship weaker", () => {
    expect(failedChecks(assessment).map((c) => c.id)).toEqual(["caption_present", "hashtags_unique"]);
  });

  it("finds the weakest markers, ties in the server's order", () => {
    expect(weakestMarkers(assessment, 3).map((m) => m.id)).toEqual([
      "visual_quality", "hook_strength", "save_worthiness",
    ]);
  });

  it("tells a scored review from checks alone", () => {
    expect(isScored(assessment)).toBe(true);
    expect(isScored({ overall: null, checks: [] })).toBe(false);
    expect(isScored(undefined)).toBe(false);
  });

  it("reads a slide number off a slide id and nothing else", () => {
    expect(slideNumber("slide-04")).toBe(4);
    expect(slideNumber("caption")).toBeNull();
    expect(slideNumber("#slide-1")).toBeNull();
  });
});
