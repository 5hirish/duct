import { describe, expect, it } from "vitest";
import {
  editableMetrics,
  lastUpdatedAt,
  metricChanges,
  metricInputs,
  metricsOf,
  metricValue,
} from "../contentMetrics.js";

// The table itself is held to the backend's by backend/tests/test_content_metrics.py;
// these cover what the form does with it.

describe("reading a metric", () => {
  it("finds a number under whichever convention wrote it", () => {
    expect(metricValue({ view_count: 900 }, "views")).toBe(900);
    expect(metricValue({ avgWatchTime: 3.1 }, "avg_watch_time")).toBe(3.1);
    expect(metricValue({ saves: 12, save_count: 40 }, "saves")).toBe(12);
    expect(metricValue({ saves: "12" }, "saves")).toBeNull();
  });

  it("names every metric the same way the backend does", () => {
    expect(metricsOf({ view_count: 5, saves: 2 })).toMatchObject({ views: 5, saves: 2, reach: null });
  });
});

describe("the form", () => {
  it("asks for the four counts only when PostBridge did not publish the post", () => {
    expect(editableMetrics({ post_bridge_post_id: "pb_1" })).toEqual([
      "saves", "reach", "avg_watch_time", "completion_rate",
    ]);
    expect(editableMetrics({ post_bridge_post_id: "" })).toHaveLength(8);
  });

  it("sends only what changed, and null for a cleared value", () => {
    const perf = { view_count: 900, saves: 12, reach: 800 };
    const names = ["saves", "reach", "avg_watch_time"];
    const inputs = { ...metricInputs(perf, names), saves: "15", reach: "", avg_watch_time: "4.5" };
    expect(metricChanges(inputs, perf, names)).toEqual({ saves: 15, reach: null, avg_watch_time: 4.5 });
  });

  it("sends nothing for an untouched form, so no synced number is marked typed-in", () => {
    const perf = { saves: 12, completionRate: 40 };
    const names = ["saves", "completion_rate", "reach"];
    expect(metricChanges(metricInputs(perf, names), perf, names)).toEqual({});
  });

  it("dates the numbers by whichever writer touched them last", () => {
    expect(lastUpdatedAt({
      last_synced_at: "2026-09-20T10:00:00Z",
      manual_updated_at: "2026-09-24T10:00:00Z",
    })).toBe("2026-09-24T10:00:00.000Z");
    expect(lastUpdatedAt({})).toBeNull();
  });
});
