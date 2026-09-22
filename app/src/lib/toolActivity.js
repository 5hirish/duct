"use client";

/**
 * What the agent did, as the transcript shows it.
 *
 * The backend sends one TOOL_ACTIVITY per allowlisted tool call, twice
 * (running, then the verdict), with structured fields and no prose — see
 * `backend/agents/core/activity.py`. This module is the client half: it
 * normalises an event into the row the chat renders, groups a burst of them,
 * and rebuilds the same rows from a stored thread, where the only record is
 * the recorder's raw `tool_use` / `tool_result` pairs.
 *
 * Two paths, one shape, on purpose. A reopened thread that showed a different
 * set of rows from the live one would make the transcript a worse record than
 * the database it came from — which is exactly what the Data pane did before
 * `insightsHistory` was written to match it.
 */

import { ActivityKind } from "./agentEvents";
import { StepStatus } from "./agentSteps";
import { mediaUrl } from "./contentApi";

const TOOL_USE = "tool_use";
const TOOL_RESULT = "tool_result";
// A sub-agent's answer, as much of it as belongs in a transcript row. The
// backend caps its own copy at the same length (agents/core/activity.py).
const SUMMARY_CHARS = 140;

/**
 * Tool name → kind, the client's copy of the backend allowlist.
 *
 * It exists for the replay path only: a live run is told the kind. Keeping
 * the two in step is the same discipline the event enums are under, and
 * `backend/tests/test_app_event_contract.py` reads this table to enforce it.
 */
export const ACTIVITY_TOOLS = Object.freeze({
  FetchData: ActivityKind.DATA,
  WebSearch: ActivityKind.WEB_SEARCH,
  WebFetch: ActivityKind.WEB_FETCH,
  FetchPages: ActivityKind.WEB_FETCH,
  generate_image: ActivityKind.IMAGE,
  edit_image: ActivityKind.IMAGE,
  render_slide: ActivityKind.SLIDE,
  task: ActivityKind.SUBAGENT,
  SearchMemory: ActivityKind.MEMORY,
  GetMemory: ActivityKind.MEMORY,
  ListDataSources: ActivityKind.CONTEXT,
  GetArtifact: ActivityKind.ARTIFACT,
  ListArtifacts: ActivityKind.ARTIFACT,
  ProjectContext: ActivityKind.CONTEXT,
  fetch_brand_context: ActivityKind.CONTEXT,
  fetch_topic_bank: ActivityKind.CONTEXT,
  fetch_format_library: ActivityKind.CONTEXT,
  fetch_avatar_library: ActivityKind.CONTEXT,
  fetch_content_history: ActivityKind.CONTEXT,
  fetch_content_assets: ActivityKind.CONTEXT,
  fetch_discovered_references: ActivityKind.CONTEXT,
  fetch_post: ActivityKind.CONTEXT,
  fetch_slide_context: ActivityKind.CONTEXT,
  submit_plan: ActivityKind.ACTION,
  submit_post_draft: ActivityKind.ACTION,
  edit_slide: ActivityKind.ACTION,
  publish_post: ActivityKind.ACTION,
  mark_posted: ActivityKind.ACTION,
  log_metrics: ActivityKind.ACTION,
});

// The runner's own notice that the turn was enriched, not a tool the model
// called (agents/core/activity.PROJECT_CONTEXT_TOOL).
export const PROJECT_CONTEXT_TOOL = "ProjectContext";

/** The stored CONTEXT row → the "Read project context" row the run drew
 *  live. Only the blocks the run had something for; a resume's row is a
 *  review record, not a second notice. Null when there is nothing to say. */
export function contextActivity(data, id = "") {
  if (!data || typeof data !== "object" || data.resume) return null;
  const blocks = data.blocks && typeof data.blocks === "object" ? data.blocks : {};
  const present = Object.entries(blocks)
    .filter(([, v]) => !(v == null || v === "" || v === false || (Array.isArray(v) && !v.length) || (typeof v === "object" && !Array.isArray(v) && !Object.keys(v).length)))
    .map(([k]) => k);
  return {
    id: id || `context-${present.join("-")}`,
    kind: ActivityKind.CONTEXT,
    tool: PROJECT_CONTEXT_TOOL,
    status: StepStatus.SUCCESS,
    title: "",
    subtitle: "",
    source: "",
    meta: { blocks: present, resume: false },
    error: "",
    reason: "",
  };
}

/** A live event as the transcript row. Unknown kinds are dropped, not guessed
 *  at: an app deployed behind the backend should stay quiet about a card it
 *  cannot draw, the way it does for an unknown step id. */
export function activityFromEvent(event) {
  const kind = event?.kind || "";
  if (!Object.values(ActivityKind).includes(kind)) return null;
  const meta = event.meta && typeof event.meta === "object" ? event.meta : {};
  return {
    id: event.activity_id || "",
    kind,
    tool: event.tool || "",
    status: event.status || StepStatus.RUNNING,
    title: event.title || "",
    subtitle: event.subtitle || "",
    source: event.source || "",
    // A picture's address is resolved here, once, where every other client of
    // the media routes resolves it: the backend sends the path it stored
    // (`/uploads/…`), and the API that serves it is not the origin the app is
    // on. A component that took the raw path would render a broken image on
    // the desktop shell, whose API is a loopback port.
    meta: Array.isArray(meta.images) ? { ...meta, images: meta.images.map(mediaUrl) } : meta,
    error: event.error || "",
    reason: event.reason || "",
  };
}

/** The recorder stores a tool's return as the JSON string it handed the model;
 *  anything else (content blocks, an over-cap preview) yields null and the
 *  caller falls back to the call's own arguments. */
function envelope(result) {
  if (result && typeof result === "object" && !Array.isArray(result)) return result;
  if (typeof result !== "string") return null;
  try {
    const parsed = JSON.parse(result);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function host(url) {
  try {
    return new URL(/^https?:\/\//i.test(url) ? url : `https://${url}`).hostname;
  } catch {
    return "";
  }
}

function rowCount(data) {
  if (Array.isArray(data)) return data.length;
  if (data && typeof data === "object") {
    for (const key of ["rows", "items", "results"]) {
      if (Array.isArray(data[key])) return data[key].length;
    }
  }
  return null;
}

/** A listing's size: its own `count`, else the first list at the top level. */
function listLen(env) {
  if (!env) return null;
  if (typeof env.count === "number") return env.count;
  for (const value of Object.values(env)) {
    if (Array.isArray(value)) return value.length;
  }
  return null;
}

/** The backend's verdict rule (`_ok`): an envelope with a status says so;
 *  the rest go by the harness's error flag. */
function okOf(env, isError) {
  if (env && "status" in env) return ["ok", "received", "success"].includes(env.status);
  return !isError;
}

/** One stored call → the row it was live. `args` is the recorded input, `env`
 *  the parsed result envelope (null when it could not be parsed). */
function replayRow({ tool, id, args, env, raw, isError }) {
  const kind = ACTIVITY_TOOLS[tool];
  const ok = okOf(env, isError);
  const base = { id, kind, tool, status: ok ? StepStatus.SUCCESS : StepStatus.ERROR, meta: {}, error: "", reason: "" };
  if (tool === "FetchPages") {
    const urls = (Array.isArray(args.urls) ? args.urls : []).filter(Boolean);
    const pages = Array.isArray(env?.pages) ? env.pages : [];
    const errors = Array.isArray(env?.errors) ? env.errors : [];
    const some = !isError && (pages.length > 0 || errors.length === 0);
    return {
      ...base,
      status: some ? StepStatus.SUCCESS : StepStatus.ERROR,
      title: urls.length ? host(urls[0]) : "",
      meta: { urls, count: env ? pages.length : urls.length, failed: errors.length },
      error: some ? "" : errors.slice(0, 3).join("; "),
    };
  }
  if (kind === ActivityKind.MEMORY) {
    if (tool === "GetMemory") {
      const memory = env?.memory && typeof env.memory === "object" ? env.memory : null;
      return {
        ...base,
        status: memory && ok ? StepStatus.SUCCESS : StepStatus.ERROR,
        title: memory?.title || args.memory_id || "",
        meta: { read: true, memory_id: memory?.memory_id || memory?.id || "" },
        error: memory && ok ? "" : String(env?.message || ""),
      };
    }
    const count = typeof env?.count === "number" ? env.count : null;
    return { ...base, title: args.query || "", meta: count === null ? {} : { count }, error: ok ? "" : String(env?.message || "") };
  }
  if (kind === ActivityKind.CONTEXT) {
    const count = ok ? listLen(env) : null;
    return {
      ...base,
      title: args.post_id || args.slide_id || args.query || "",
      meta: count === null ? {} : { count },
      error: ok ? "" : String(env?.message || ""),
    };
  }
  if (kind === ActivityKind.ARTIFACT) {
    if (tool === "ListArtifacts") {
      const rows = Array.isArray(env?.artifacts) ? env.artifacts : [];
      return { ...base, status: isError ? StepStatus.ERROR : StepStatus.SUCCESS, title: "", meta: { listing: true, count: rows.length } };
    }
    const found = Boolean(env?.artifact_id) && !isError;
    return {
      ...base,
      status: found ? StepStatus.SUCCESS : StepStatus.ERROR,
      title: env?.title || args.artifact_id || "",
      meta: { artifact_id: env?.artifact_id || args.artifact_id || "", kind: env?.kind || "", version: typeof env?.version === "number" ? env.version : null },
      error: found ? "" : (typeof raw === "string" && !env ? raw.trim() : String(env?.message || "")),
    };
  }
  if (kind === ActivityKind.ACTION) {
    const meta = {};
    for (const key of ["post_id", "slide_id", "status", "scheduled_at"]) if (env?.[key]) meta[key] = String(env[key]);
    // The row names the thing by its words (a topic, a headline), never by
    // a row id the person has no way to read.
    return {
      ...base,
      title: env?.topic || env?.headline || args.title || args.topic || "",
      meta,
      error: ok ? "" : String(env?.message || env?.error || ""),
    };
  }
  if (kind === ActivityKind.DATA) {
    const meta = {
      date_from: env?.date_from || args.date_from || "",
      date_to: env?.date_to || args.date_to || "",
    };
    const rows = rowCount(env?.data);
    if (rows !== null) meta.rows = rows;
    return {
      ...base,
      title: env?.entity_id || args.entity_id || "",
      source: env?.connector_id || String(env?.entity_id || args.entity_id || "").split("_")[0],
      meta,
      error: ok ? "" : String(env?.message || ""),
      reason: ok ? "" : String(env?.status || ""),
    };
  }
  if (kind === ActivityKind.WEB_SEARCH) {
    const sources = Array.isArray(env?.sources) ? env.sources : [];
    return {
      ...base,
      title: env?.query || args.query || "",
      meta: {
        sources: sources.map((s) => ({ title: s?.title || host(s?.url || ""), url: s?.url || "" })),
        source_count: sources.length,
        grounded: Boolean(env?.grounded),
      },
      error: ok ? "" : String(env?.message || ""),
    };
  }
  if (kind === ActivityKind.WEB_FETCH) {
    const url = env?.url || args.url || "";
    return {
      ...base,
      title: host(url) || url,
      meta: { url, truncated: Boolean(env?.truncated) },
      error: ok ? "" : String(env?.message || ""),
    };
  }
  if (kind === ActivityKind.IMAGE) {
    const images = (Array.isArray(env?.asset_urls) ? env.asset_urls : []).filter(Boolean).map(mediaUrl);
    return {
      ...base,
      status: images.length && !isError ? StepStatus.SUCCESS : StepStatus.ERROR,
      title: args.prompt || "",
      meta: { images, model: env?.model || "", attached_to: env?.attached_to || "" },
    };
  }
  if (kind === ActivityKind.SLIDE) {
    const url = env?.asset_url || "";
    return {
      ...base,
      status: url && !isError ? StepStatus.SUCCESS : StepStatus.ERROR,
      title: env?.slide_id || args.slide_id || "",
      meta: { images: url ? [mediaUrl(url)] : [], note: env?.note || "" },
    };
  }
  // Sub-agent: what comes back is the agent's own answer, in prose — there is
  // no envelope to parse, and the answer is the whole point of the row.
  return {
    ...base,
    title: args.subagent_type || "agent",
    meta: {
      brief: args.description || "",
      summary: typeof raw === "string" ? raw.trim().slice(0, SUMMARY_CHARS) : "",
    },
  };
}

/**
 * Every allowlisted call's arguments, by tool_use_id.
 *
 * A stored result carries its own envelope but not what was asked for, and
 * the two together make a better row than either — "landing pages" comes
 * from the call, the window and the verdict from the result.
 */
export function activityCallIndex(events) {
  const calls = new Map();
  for (const ev of events || []) {
    if (ev?.kind === TOOL_USE && ev.data?.tool_use_id && ACTIVITY_TOOLS[ev.data.name]) {
      calls.set(ev.data.tool_use_id, ev.data.input && typeof ev.data.input === "object" ? ev.data.input : {});
    }
  }
  return calls;
}

/**
 * One stored row → the activity row it was live, or null when it is not one.
 *
 * Only a `tool_result` makes a row: a `tool_use` with no result is a run that
 * was cut off, and a card stuck on "running" for ever is worse than no card.
 */
export function activityFromStored(ev, calls) {
  if (ev?.kind !== TOOL_RESULT) return null;
  const tool = ev.data?.name || "";
  if (!ACTIVITY_TOOLS[tool]) return null;
  const id = ev.data.tool_use_id || "";
  return replayRow({
    tool,
    id: id || `${tool}-${calls?.size ?? 0}`,
    args: calls?.get(id) || {},
    env: envelope(ev.data.result),
    raw: ev.data.result,
    isError: Boolean(ev.data.is_error),
  });
}

/** Stored conversation rows (`{ kind, data }`) → activity rows, in order. */
export function activitiesFromEvents(events) {
  const calls = activityCallIndex(events);
  const out = [];
  for (const ev of events || []) {
    const row = activityFromStored(ev, calls);
    if (row) out.push(row);
  }
  return out;
}

/**
 * The thread's data pulls, deduped, newest window per source kept — what the
 * Data pane lists once the transcript carries the rows themselves. Grouped by
 * connector so a run that read GA4 four times reads as one source, four
 * windows, rather than four unrelated lines.
 */
export function dataSourceRollup(activities) {
  const groups = new Map();
  for (const row of activities || []) {
    if (row.kind !== ActivityKind.DATA) continue;
    const key = row.source || row.title;
    const group = groups.get(key) || { source: key, rows: [], ok: 0, failed: 0 };
    const seen = group.rows.some(
      (r) => r.title === row.title && r.meta?.date_from === row.meta?.date_from,
    );
    if (!seen) {
      group.rows.push(row);
      if (row.status === StepStatus.ERROR) group.failed += 1;
      else group.ok += 1;
    }
    groups.set(key, group);
  }
  return [...groups.values()];
}

/**
 * Consecutive activity rows, collapsed into one block for rendering.
 *
 * A grouping pass rather than a reducer change: the transcript is a list of
 * rows and must stay one (hydration, replay and the streaming tail all index
 * into it), while "four pulls in a row are one action" is a question about
 * how it looks, which is the renderer's.
 */
export function groupActivityRows(messages, activityRole) {
  const out = [];
  for (const msg of messages || []) {
    const last = out[out.length - 1];
    if (msg?.role !== activityRole) {
      out.push(msg);
      continue;
    }
    if (last?.group) last.activities.push(msg.activity);
    else out.push({ group: true, role: activityRole, activities: [msg.activity] });
  }
  return out;
}
