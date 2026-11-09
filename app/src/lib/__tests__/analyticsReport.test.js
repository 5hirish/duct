import { describe, expect, it } from "vitest";

import {
  ReportState,
  SourceStatus,
  chartRows,
  defaultSelection,
  drawableBlocks,
  reconcileSelection,
  reportState,
  tableColumns,
  ttlHours,
} from "../analyticsReport.js";

const ready = (id) => ({ id, label: id, status: SourceStatus.READY });
const off = (id) => ({ id, label: id, status: SourceStatus.NOT_CONNECTED });

describe("reportState", () => {
  it("is empty until something can be read, then until something was written", () => {
    expect(reportState({ sources: [off("gsc")], report: null })).toBe(ReportState.NO_SOURCES);
    expect(reportState({ sources: [ready("gsc")], report: null })).toBe(ReportState.EMPTY);
  });

  it("a run under way outranks a stale copy, and an error outranks a fresh one", () => {
    const stale = { stale: true, report: {} };
    expect(reportState({ sources: [ready("gsc")], report: stale, generating: true })).toBe(ReportState.GENERATING);
    expect(reportState({ sources: [ready("gsc")], report: { stale: false }, error: { code: "x" } })).toBe(ReportState.FAILED);
    expect(reportState({ sources: [ready("gsc")], report: stale })).toBe(ReportState.STALE);
    expect(reportState({ sources: [ready("gsc")], report: { stale: false } })).toBe(ReportState.FRESH);
  });

  it("falls back to a day when the payload carries no ttl", () => {
    expect(ttlHours({})).toBe(24);
    expect(ttlHours({ ttl_hours: 6 })).toBe(6);
  });
});

describe("selection", () => {
  it("starts with every ready source and drops what stopped being ready", () => {
    const sources = [ready("gsc"), off("ga4"), ready("publishers")];
    expect(defaultSelection(sources)).toEqual(["gsc", "publishers"]);
    expect(reconcileSelection(["gsc", "ga4"], sources)).toEqual(["gsc"]);
  });

  it("never leaves nothing selected while something is ready", () => {
    expect(reconcileSelection(["ga4"], [ready("gsc")])).toEqual(["gsc"]);
  });
});

describe("blocks", () => {
  it("coerces the measure to a number and drops rows that have none", () => {
    const rows = chartRows({ x_field: "d", y_field: "n", rows: [{ d: "a", n: "1,200" }, { d: "b", n: null }, { d: "c", n: 3 }] });
    expect(rows.map((r) => r.__value)).toEqual([1200, 3]);
  });

  it("keeps only blocks the app can draw with something in them", () => {
    const body = {
      blocks: [
        { block_type: "kpi_strip", kpis: [] },
        { block_type: "kpi_strip", kpis: [{ label: "x", value: "1" }] },
        { block_type: "heatmap", rows: [{ a: 1 }] },
        { block_type: "bar_chart", x_field: "a", y_field: "b", rows: [{ a: "x", b: 1 }] },
        { block_type: "table", rows: [] },
      ],
    };
    expect(drawableBlocks(body).map((b) => b.block_type)).toEqual(["kpi_strip", "bar_chart"]);
  });

  it("puts the named fields first in a table and caps at six columns", () => {
    const block = { x_field: "query", y_field: "clicks", rows: [{ impressions: 1, clicks: 2, query: "q", ctr: 3, position: 4, a: 5, b: 6 }] };
    expect(tableColumns(block)).toEqual(["query", "clicks", "impressions", "ctr", "position", "a"]);
  });
});
