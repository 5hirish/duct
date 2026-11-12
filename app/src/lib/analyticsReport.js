/**
 * The Analytics tab's report, as state the components draw from.
 *
 * Dependency-free so it runs in vitest as plain functions (lib/desk.js's
 * arrangement). The backend answers one payload (`getAnalyticsReport`); this
 * reads it into the one state the tab is in, the sources a person may tick,
 * and the rows a block draws, so the components only draw what it returns.
 * The copy for each state lives with the component as `msg` tables — this
 * module returns codes.
 */

/** Where a source stands, mirrored from agents/insights/report_templates.py. */
export const SourceStatus = Object.freeze({
  READY: "ready",
  NEEDS_ACCOUNT: "needs_account",
  NEEDS_ATTENTION: "needs_attention",
  NOT_CONNECTED: "not_connected",
});

/** The one state the tab is in. Order matters: a run under way outranks a stale copy. */
export const ReportState = Object.freeze({
  NO_SOURCES: "no_sources",   // nothing ready to read from
  EMPTY: "empty",             // sources ready, never written
  GENERATING: "generating",   // a run is writing it; the old copy, if any, stays on screen
  FAILED: "failed",           // the last run ended in an error; the old copy, if any, stays
  FRESH: "fresh",
  STALE: "stale",             // older than the server's TTL; served, with Refresh offered
});

/** The block types the app draws; anything else is skipped, never crashes a report. */
export const BLOCK_TYPES = Object.freeze([
  "kpi_strip", "time_series", "bar_chart", "pie_chart", "table", "signal_list", "action_list",
]);

/** The server's TTL, mirrored for a payload that predates `ttl_hours`. */
const DEFAULT_TTL_HOURS = 24;

export function readySources(sources = []) {
  return (Array.isArray(sources) ? sources : []).filter((s) => s?.status === SourceStatus.READY);
}

/**
 * The sources ticked by default: every ready one. A person untick­ing one is
 * a choice the component keeps; this is the starting point when the template
 * changes or the payload first lands.
 */
export function defaultSelection(sources = []) {
  return readySources(sources).map((s) => s.id);
}

/**
 * Keep a selection honest against the sources the server now lists: drop ids
 * that are no longer ready, and start from every ready source when nothing
 * selected survives (a selection of nothing is a run that cannot start).
 */
export function reconcileSelection(selected = [], sources = []) {
  const ready = new Set(defaultSelection(sources));
  const kept = (Array.isArray(selected) ? selected : []).filter((id) => ready.has(id));
  return kept.length ? kept : [...ready];
}

export function reportState(payload) {
  if (!payload) return ReportState.EMPTY;
  const hasSources = readySources(payload.sources).length > 0;
  if (payload.generating) return ReportState.GENERATING;
  if (payload.error) return ReportState.FAILED;
  if (!payload.report) return hasSources ? ReportState.EMPTY : ReportState.NO_SOURCES;
  return payload.report.stale ? ReportState.STALE : ReportState.FRESH;
}

/** The hours until a fresh report is treated as stale, for the status line. */
export function ttlHours(payload) {
  const n = Number(payload?.ttl_hours);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_TTL_HOURS;
}

/** The report body the blocks draw, or null. */
export function reportBody(payload) {
  const body = payload?.report?.report;
  return body && typeof body === "object" ? body : null;
}

function toNumber(value) {
  // Number(null) and Number("") are 0, which would draw a missing value as
  // a real zero on the chart.
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * A block's rows with the y field numeric and the x field a string, bad rows
 * dropped. The model wrote the rows; a row without a number for the measure
 * is a row the chart cannot draw and a row with a number as a string
 * ("1,200") is one it would draw at zero.
 */
export function chartRows(block) {
  const x = block?.x_field;
  const y = block?.y_field;
  if (!x || !y || !Array.isArray(block.rows)) return [];
  return block.rows
    .map((row) => {
      const value = toNumber(typeof row?.[y] === "string" ? row[y].replace(/[,\s%]/g, "") : row?.[y]);
      if (value === null || row?.[x] === undefined || row?.[x] === null) return null;
      return { ...row, [x]: String(row[x]), __value: value };
    })
    .filter(Boolean);
}

/** The columns a table block shows: the fields named, else the first six keys. */
export function tableColumns(block) {
  const named = [block?.x_field, block?.group_by, block?.y_field].filter(Boolean);
  if (named.length) {
    const rest = Object.keys(block?.rows?.[0] || {}).filter((k) => !named.includes(k));
    return [...named, ...rest].slice(0, 6);
  }
  return Object.keys(block?.rows?.[0] || {}).slice(0, 6);
}

/** Blocks the app can draw, in the report's order, each with something in it. */
export function drawableBlocks(body) {
  const blocks = Array.isArray(body?.blocks) ? body.blocks : [];
  return blocks.filter((b) => {
    if (!BLOCK_TYPES.includes(b?.block_type)) return false;
    if (b.block_type === "kpi_strip") return Array.isArray(b.kpis) && b.kpis.length > 0;
    if (b.block_type === "signal_list") return Array.isArray(b.signals) && b.signals.length > 0;
    if (b.block_type === "action_list") return Array.isArray(b.actions) && b.actions.length > 0;
    if (b.block_type === "table") return Array.isArray(b.rows) && b.rows.length > 0;
    return chartRows(b).length > 0;
  });
}

/**
 * The sources the report says it read, as `{ id, label, status }`, so the
 * footer can say what the numbers rest on without re-deriving it.
 */
export function sourcesUsed(body) {
  return (Array.isArray(body?.sources) ? body.sources : [])
    .filter((s) => s && typeof s === "object" && s.id)
    .map((s) => ({ id: String(s.id), label: String(s.label || s.id), status: String(s.status || "read"), note: String(s.note || "") }));
}
