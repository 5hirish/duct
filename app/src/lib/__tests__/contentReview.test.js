import { describe, expect, it } from "vitest";

import {
  failedChecks,
  hookVotes,
  isScored,
  panelEchoesBaseline,
  panelTrusted,
  replyNumber,
  slideNumber,
  weakestMarkers,
} from "../contentReview";

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
    expect(replyNumber("reply-2")).toBe(2);
    expect(replyNumber("slide-02")).toBeNull();
    expect(replyNumber("caption")).toBeNull();
  });

  it("shows the panel's verdicts only once it beat a coin on past posts", () => {
    expect(panelTrusted({ panel_check: { fit: "tracks" } })).toBe(true);
    expect(panelTrusted({ panel_check: { fit: "loose" } })).toBe(true);
    expect(panelTrusted({ panel_check: { fit: "chance" } })).toBe(false);
    expect(panelTrusted({ panel_check: null })).toBe(false);
  });

  it("counts each opening's picks and ignores a pick that names none", () => {
    const review = { hooks: ["a", "b"], personas: [{ pick: 1 }, { pick: 1 }, { pick: 5 }, { pick: null }] };
    expect(hookVotes(review)).toEqual([0, 2]);
  });

  it("notices a panel that reacts exactly like anyone scrolling", () => {
    const base = { stop: "maybe", save: "no", click: "no", pick: 0 };
    expect(panelEchoesBaseline({ baseline: base, personas: [{ ...base }, { ...base }] })).toBe(true);
    expect(panelEchoesBaseline({ baseline: base, personas: [{ ...base }, { ...base, save: "yes" }] })).toBe(false);
    expect(panelEchoesBaseline({ baseline: null, personas: [{ ...base }] })).toBe(false);
  });
});
