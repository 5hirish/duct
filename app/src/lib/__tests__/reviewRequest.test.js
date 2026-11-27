import { describe, expect, it } from "vitest";
import { REVIEW_IDLE, ReviewStop, START_WINDOW_MS, isReviewing, reviewAsked, reviewTick } from "../reviewRequest.js";

const asked = reviewAsked("2026-11-27T10:00:00Z", 0);
const at = (state, over) => reviewTick(state, { idle: true, failed: false, scoredAt: "2026-11-27T10:00:00Z", now: 1000, ...over });

describe("a requested review", () => {
  it("is under way until a new score lands", () => {
    const running = at(asked, { idle: false });
    expect(isReviewing(running)).toBe(true);
    expect(at(running, { idle: false, scoredAt: "2026-11-27T10:05:00Z" })).toEqual(REVIEW_IDLE);
  });

  it("stops when the turn ends with no new score", () => {
    const running = at(asked, { idle: false });
    const ended = at(running, { idle: true });
    expect(isReviewing(ended)).toBe(false);
    expect(ended.stopped).toBe(ReviewStop.ENDED);
  });

  it("stops when the run fails", () => {
    expect(at(at(asked, { idle: false }), { idle: false, failed: true }).stopped).toBe(ReviewStop.FAILED);
  });

  it("waits a moment for the turn to start, then gives up", () => {
    expect(isReviewing(at(asked, { now: START_WINDOW_MS - 1 }))).toBe(true);
    expect(at(asked, { now: START_WINDOW_MS }).stopped).toBe(ReviewStop.NOT_STARTED);
  });

  it("counts a first review from a post never scored", () => {
    const first = reviewAsked("", 0);
    expect(isReviewing(at(first, { idle: false, scoredAt: "" }))).toBe(true);
    expect(at(first, { scoredAt: "2026-11-27T10:05:00Z" })).toEqual(REVIEW_IDLE);
  });
});
