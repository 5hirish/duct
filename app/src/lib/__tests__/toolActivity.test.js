import { describe, expect, it } from "vitest";
import { ActivityKind } from "../agentEvents";
import { StepStatus } from "../agentSteps";
import {
  activitiesFromEvents,
  contextActivity,
  activityFromEvent,
  dataSourceRollup,
  groupActivityRows,
} from "../toolActivity";

const use = (name, id, input) => ({ kind: "tool_use", data: { name, tool_use_id: id, input } });
const result = (name, id, payload, isError = false) => ({
  kind: "tool_result",
  data: { name, tool_use_id: id, result: JSON.stringify(payload), is_error: isError },
});

describe("activityFromEvent", () => {
  it("keeps the fields the card draws", () => {
    const row = activityFromEvent({
      activity_id: "t1",
      kind: "data",
      tool: "FetchData",
      status: "success",
      title: "ga4_landing_pages",
      source: "ga4",
      meta: { rows: 842 },
    });
    expect(row).toMatchObject({ id: "t1", kind: ActivityKind.DATA, source: "ga4", meta: { rows: 842 } });
  });

  it("drops a kind this build cannot draw rather than guessing", () => {
    expect(activityFromEvent({ activity_id: "t1", kind: "hologram" })).toBeNull();
  });
});

describe("activitiesFromEvents", () => {
  it("rebuilds a pull from the stored call and its envelope", () => {
    const rows = activitiesFromEvents([
      use("FetchData", "t1", { entity_id: "ga4_landing_pages", date_from: "2026-08-18" }),
      result("FetchData", "t1", {
        status: "ok",
        entity_id: "ga4_landing_pages",
        connector_id: "ga4",
        date_from: "2026-08-18",
        date_to: "2026-09-16",
        data: { rows: [1, 2, 3] },
      }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: ActivityKind.DATA,
      status: StepStatus.SUCCESS,
      source: "ga4",
      title: "ga4_landing_pages",
      meta: { date_from: "2026-08-18", date_to: "2026-09-16", rows: 3 },
    });
  });

  it("carries the provider's own sentence and the status that explains it", () => {
    const [row] = activitiesFromEvents([
      use("FetchData", "t2", { entity_id: "google_ads_campaigns" }),
      result("FetchData", "t2", {
        status: "reauth_required",
        entity_id: "google_ads_campaigns",
        connector_id: "google_ads",
        message: "google_ads rejected its stored credential.",
      }),
    ]);
    expect(row.status).toBe(StepStatus.ERROR);
    expect(row.reason).toBe("reauth_required");
    expect(row.error).toContain("rejected its stored credential");
  });

  it("reads a search's sources back", () => {
    const [row] = activitiesFromEvents([
      use("WebSearch", "t3", { query: "LiteLLM self-hosted" }),
      result("WebSearch", "t3", {
        status: "ok",
        query: "LiteLLM self-hosted",
        grounded: true,
        sources: [{ title: "docs.litellm.ai", url: "https://docs.litellm.ai/x" }],
      }),
    ]);
    expect(row.kind).toBe(ActivityKind.WEB_SEARCH);
    expect(row.meta.sources).toEqual([{ title: "docs.litellm.ai", url: "https://docs.litellm.ai/x" }]);
  });

  it("ignores tools that are not on the allowlist", () => {
    // RememberFact has its own row (the "Remembered" note); write_todos has the strip.
    expect(activitiesFromEvents([
      use("RememberFact", "t4", { title: "pricing" }),
      result("RememberFact", "t4", { status: "ok" }),
      use("write_todos", "t5", { todos: [] }),
      result("write_todos", "t5", { status: "ok" }),
    ])).toEqual([]);
  });

  it("drops a call that never returned, rather than leaving it running", () => {
    expect(activitiesFromEvents([use("FetchData", "t5", { entity_id: "gsc_queries" })])).toEqual([]);
  });
});

describe("dataSourceRollup", () => {
  it("groups by connector and counts each verdict once", () => {
    const rows = activitiesFromEvents([
      use("FetchData", "a", { entity_id: "ga4_landing_pages" }),
      result("FetchData", "a", { status: "ok", entity_id: "ga4_landing_pages", connector_id: "ga4", date_from: "2026-08-18" }),
      use("FetchData", "b", { entity_id: "ga4_traffic" }),
      result("FetchData", "b", { status: "ok", entity_id: "ga4_traffic", connector_id: "ga4", date_from: "2026-08-18" }),
      use("FetchData", "c", { entity_id: "google_ads_campaigns" }),
      result("FetchData", "c", { status: "fetch_failed", entity_id: "google_ads_campaigns", connector_id: "google_ads" }),
      // The same pull again — the session cache answers a repeat, and the
      // pane listed it twice before this deduped.
      use("FetchData", "d", { entity_id: "ga4_traffic" }),
      result("FetchData", "d", { status: "ok", entity_id: "ga4_traffic", connector_id: "ga4", date_from: "2026-08-18" }),
    ]);
    const groups = dataSourceRollup(rows);
    expect(groups.map((g) => g.source)).toEqual(["ga4", "google_ads"]);
    expect(groups[0]).toMatchObject({ ok: 2, failed: 0 });
    expect(groups[1]).toMatchObject({ ok: 0, failed: 1 });
  });
});

describe("groupActivityRows", () => {
  it("folds a burst into one block and leaves the prose either side alone", () => {
    const grouped = groupActivityRows(
      [
        { role: "assistant", text: "Reading your data." },
        { role: "activity", activity: { id: "1" } },
        { role: "activity", activity: { id: "2" } },
        { role: "assistant", text: "Here is what it says." },
        { role: "activity", activity: { id: "3" } },
      ],
      "activity",
    );
    expect(grouped).toHaveLength(4);
    expect(grouped[1].activities.map((a) => a.id)).toEqual(["1", "2"]);
    expect(grouped[3].activities.map((a) => a.id)).toEqual(["3"]);
  });
});

describe("the wider allowlist", () => {
  it("draws the audit's page read as one row naming the site and what failed", () => {
    const [row] = activitiesFromEvents([
      use("FetchPages", "p1", { urls: ["https://acme.io/", "https://acme.io/pricing", "https://acme.io/x"] }),
      result("FetchPages", "p1", { pages: [{ url: "https://acme.io/" }, { url: "https://acme.io/pricing" }], errors: ["https://acme.io/x: 404"] }),
    ]);
    expect(row).toMatchObject({ kind: ActivityKind.WEB_FETCH, status: StepStatus.SUCCESS, title: "acme.io", meta: { count: 2, failed: 1 } });
    expect(row.meta.urls).toHaveLength(3);
  });

  it("says what memory was asked and how much it had, never the entries", () => {
    const [row] = activitiesFromEvents([
      use("SearchMemory", "m1", { query: "pricing" }),
      result("SearchMemory", "m1", { count: 2, memories: [{ title: "Pricing changed" }] }),
    ]);
    expect(row).toMatchObject({ kind: ActivityKind.MEMORY, title: "pricing", meta: { count: 2 } });
    expect(JSON.stringify(row)).not.toContain("Pricing changed");
  });

  it("counts a listing and names an opened document", () => {
    const rows = activitiesFromEvents([
      use("ListDataSources", "c1", {}),
      result("ListDataSources", "c1", { status: "ok", sources: [{ id: "ga4" }, { id: "gsc" }] }),
      use("GetArtifact", "a1", { artifact_id: "x" }),
      result("GetArtifact", "a1", { artifact_id: "x", title: "Organic growth", kind: "brief", version: 3 }),
      use("GetArtifact", "a2", { artifact_id: "gone" }),
      { kind: "tool_result", data: { name: "GetArtifact", tool_use_id: "a2", result: "No artifact 'gone' in this project.", is_error: false } },
    ]);
    expect(rows[0]).toMatchObject({ kind: ActivityKind.CONTEXT, tool: "ListDataSources", meta: { count: 2 } });
    expect(rows[1]).toMatchObject({ kind: ActivityKind.ARTIFACT, title: "Organic growth", meta: { artifact_id: "x", version: 3 } });
    expect(rows[2]).toMatchObject({ kind: ActivityKind.ARTIFACT, status: StepStatus.ERROR, error: "No artifact 'gone' in this project." });
  });

  it("draws what the content agent did on the person's behalf", () => {
    const [row] = activitiesFromEvents([
      use("publish_post", "x1", { post_id: "p1" }),
      result("publish_post", "x1", { status: "ok", post_id: "p1", scheduled_at: "2026-09-23T09:00:00Z" }),
    ]);
    expect(row).toMatchObject({ kind: ActivityKind.ACTION, tool: "publish_post", status: StepStatus.SUCCESS, meta: { post_id: "p1", status: "ok" } });
  });
});

describe("contextActivity", () => {
  it("names only the blocks the run had something for, and stays quiet on a resume", () => {
    const row = contextActivity({ resume: false, blocks: { business_context: "Acme…", memory: "", data_sources: "ga4", compress: false } }, "c1");
    expect(row).toMatchObject({ id: "c1", kind: ActivityKind.CONTEXT, tool: "ProjectContext", meta: { blocks: ["business_context", "data_sources"] } });
    expect(contextActivity({ resume: true, blocks: { resume_primer: "…" } })).toBeNull();
    expect(contextActivity(null)).toBeNull();
  });
});
