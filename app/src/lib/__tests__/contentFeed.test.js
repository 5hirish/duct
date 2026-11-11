import { describe, expect, it } from "vitest";
import {
  DEFAULT_FEED,
  daySources,
  feedDayCount,
  feedFromHistory,
  feedFromParams,
  feedRequest,
  feedSessionHref,
  feedSummary,
} from "../contentFeed.js";
import { LEFT_OUT_LABELS } from "../contentFeedLabels.js";

const TODAY = new Date(2026, 10, 11);

describe("the feed session URL", () => {
  it("round-trips the setup sheet's options", () => {
    const options = { sources: ["github"], lookBack: 30, horizon: 14, maxDays: 3, disclosure: "releases" };
    const href = feedSessionHref(options, TODAY);
    expect(href.startsWith("/content/sessions/new?source=work&start=2026-11-11&days=14")).toBe(true);
    expect(feedFromParams(new URL(href, "http://x").searchParams)).toEqual(options);
  });

  it("is not a feed without source=work, and bad values fall back", () => {
    expect(feedFromParams(new URLSearchParams("start=2026-11-11&days=7"))).toBe(null);
    const parsed = feedFromParams(new URLSearchParams("source=work&max=99&disclosure=all&sources=gitlab&look=5"));
    expect(parsed).toEqual({ ...DEFAULT_FEED, sources: [...DEFAULT_FEED.sources] });
  });
});

describe("the request", () => {
  it("sends a look-back only when one was picked", () => {
    expect(feedRequest(DEFAULT_FEED)).toEqual({ sources: ["github", "duct"], max_days: 2, disclosure: "shipped" });
    expect(feedRequest({ lookBack: 7 }).look_back_days).toBe(7);
  });
});

describe("the read summary", () => {
  it("orders what was left out and totals it", () => {
    const s = feedSummary({
      worth_a_plan: true,
      window: { from: "2026-10-29", to: "2026-11-11" },
      items: [{ ref: "gh:pr-412", kind: "pull_request", title: "Retry", url: "" }],
      left_out: { bot: 2, chore: 12, squashed: 0 },
    });
    expect(s.leftOut).toEqual([{ reason: "chore", count: 12 }, { reason: "bot", count: 2 }]);
    expect(s.leftOutTotal).toBe(14);
    expect(s.worth).toBe(true);
  });

  it("survives a missing payload", () => {
    expect(feedSummary(null)).toMatchObject({ worth: false, items: [], leftOut: [], leftOutTotal: 0 });
  });

  it("has a label for every reason the backend sends", () => {
    for (const code of ["bot", "dependency", "chore", "squashed", "issue", "prerelease",
      "internal_docs", "disclosure", "already_planned", "over_cap"]) {
      expect(LEFT_OUT_LABELS[code]).toBeTruthy();
    }
  });
});

describe("feed days", () => {
  it("counts the days that cite the feed", () => {
    const days = [{ sources: [{ ref: "gh:pr-1" }] }, { sources: [] }, {}, { sources: [{ title: "no ref" }] }];
    expect(feedDayCount(days)).toBe(1);
    expect(daySources(days[3])).toEqual([]);
  });

  it("reads the last stored feed row of a thread", () => {
    const events = [{ kind: "user" }, { kind: "feed", data: { worth_a_plan: false } }, { kind: "assistant" }];
    expect(feedFromHistory(events)).toEqual({ worth_a_plan: false });
    expect(feedFromHistory([])).toBe(null);
  });
});
