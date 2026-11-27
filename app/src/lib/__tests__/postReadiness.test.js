import { describe, expect, it } from "vitest";
import { nextAfterApproval, pendingSlides, readyToPublish } from "../postReadiness.js";

const done = (n) => ({ slide_id: `slide-0${n}`, kind: "photo", image_prompt: "p", image_prompt_used: "p", image_url: `/${n}.png` });
const owed = (n) => ({ slide_id: `slide-0${n}`, kind: "photo", image_prompt: "p" });
const words = (n) => ({ slide_id: `slide-0${n}`, kind: "text", headline: "h" });

describe("post readiness", () => {
  it("is ready only when no slide is owed a picture", () => {
    expect(readyToPublish([done(1), words(2), done(3)])).toBe(true);
    expect(readyToPublish([done(1), owed(2)])).toBe(false);
    expect(readyToPublish([])).toBe(false);
  });

  it("counts a picture made from an older prompt as owed", () => {
    expect(pendingSlides([done(1), { ...done(2), image_prompt: "changed" }])).toEqual([1]);
  });

  it("waits on the slide just made, and only while the agent is idle", () => {
    const slides = [done(1), done(2), owed(3), owed(4)];
    expect(nextAfterApproval(slides, 1, true)).toBe(2);
    expect(nextAfterApproval(slides, 1, false)).toBe(-1);
    expect(nextAfterApproval(slides, 0, true)).toBe(-1); // slide 2 sits between
    expect(nextAfterApproval(slides, 2, true)).toBe(-1); // still owed itself
  });

  it("waits on nothing once every slide is done", () => {
    expect(nextAfterApproval([done(1), done(2)], 1, true)).toBe(-1);
  });

  it("looks past a slide with nothing to make", () => {
    expect(nextAfterApproval([done(1), words(2), owed(3)], 0, true)).toBe(2);
  });
});
