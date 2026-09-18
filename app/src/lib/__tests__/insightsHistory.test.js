import { describe, expect, it } from "vitest";
import { fetchedFromEvents, fetchLabel } from "../insightsHistory";

const use = (id, input) => ({ kind: "tool_use", data: { name: "FetchData", tool_use_id: id, input } });
const result = (id, body, is_error = false) => ({
  kind: "tool_result",
  data: { name: "FetchData", tool_use_id: id, output: typeof body === "string" ? body : JSON.stringify(body), is_error },
});

describe("fetchedFromEvents", () => {
  it("rebuilds the live pane's rows from the stored tool traffic, in order", () => {
    const rows = fetchedFromEvents([
      { kind: "user", data: { content: "why did CPA jump?" } },
      use("t1", { entity_id: "ga4_traffic", date_from: "2026-08-20", date_to: "2026-09-17" }),
      result("t1", { status: "ok", entity_id: "ga4_traffic", date_from: "2026-08-20", date_to: "2026-09-17", data: "a,b\n1,2" }),
      use("t2", { entity_id: "google_ads_campaigns" }),
      result("t2", {
        status: "fetch_failed",
        entity_id: "google_ads_campaigns",
        date_from: "2026-08-20",
        date_to: "2026-09-17",
        message: "google_ads returned an error: quota exceeded. Do not retry the same call.",
      }),
      { kind: "assistant", data: { text: "One campaign." } },
    ]);
    expect(rows).toEqual([
      { label: "ga4 traffic · 2026-08-20 → 2026-09-17", ok: true, error: "" },
      {
        label: "google ads campaigns · 2026-08-20 → 2026-09-17",
        ok: false,
        error: "google_ads returned an error: quota exceeded. Do not retry the same call.",
      },
    ]);
  });

  it("lists a repeated pull once and ignores every other tool", () => {
    const rows = fetchedFromEvents([
      use("t1", { entity_id: "gsc_queries", date_from: "2026-09-01", date_to: "2026-09-14" }),
      result("t1", { status: "ok", entity_id: "gsc_queries", date_from: "2026-09-01", date_to: "2026-09-14" }),
      use("t2", { entity_id: "gsc_queries", date_from: "2026-09-01", date_to: "2026-09-14" }),
      result("t2", { status: "ok", entity_id: "gsc_queries", date_from: "2026-09-01", date_to: "2026-09-14" }),
      { kind: "tool_use", data: { name: "ReadConnectorNotes", tool_use_id: "n1", input: {} } },
      { kind: "tool_result", data: { name: "ReadConnectorNotes", tool_use_id: "n1", output: "{}" } },
    ]);
    expect(rows).toEqual([{ label: "gsc queries · 2026-09-01 → 2026-09-14", ok: true, error: "" }]);
  });

  it("falls back to the call's arguments and the error flag when the body is not an envelope", () => {
    const rows = fetchedFromEvents([
      use("t1", { entity_id: "mixpanel_events", date_from: "2026-09-01", date_to: "2026-09-14" }),
      result("t1", "not json at all"),
      use("t2", { entity_id: "clarity_sessions" }),
      result("t2", { _truncated: true, preview: "{" }, true),
    ]);
    expect(rows).toEqual([
      { label: "mixpanel events · 2026-09-01 → 2026-09-14", ok: true, error: "" },
      { label: "clarity sessions", ok: false, error: "" },
    ]);
  });

  it("labels the way the runner does", () => {
    expect(fetchLabel("ga4_traffic", "", "")).toBe("ga4 traffic");
    expect(fetchedFromEvents(undefined)).toEqual([]);
  });
});
