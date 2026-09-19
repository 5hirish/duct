/**
 * The Data pane, rebuilt from a stored thread.
 *
 * While a brief streams, the pane fills from `step_finished` events, one per
 * source pull. A reopened thread replays none of those — its history is the
 * transcript's rows — so the pane came back empty on the very thread whose
 * brief sits beside it. Every pull is in that history, though: the recorder
 * stores each `FetchData` call as a `tool_use` (the arguments) and a
 * `tool_result` (the JSON body the model read, envelope and all). This reads
 * those rows back into the same rows the live pane shows.
 *
 * The label is built the way the backend builds it (`_fetch_label` in the
 * insights runner): entity, then the window, because a number without its
 * window is the easiest way to state something false.
 */

const FETCH_TOOL = "FetchData";
const TOOL_USE = "tool_use";
const TOOL_RESULT = "tool_result";
const STATUS_OK = "ok";

/** One source pull, as the pane lists it. */
export function fetchLabel(entityId, dateFrom, dateTo) {
  const window = dateFrom ? ` · ${dateFrom} → ${dateTo}` : "";
  return `${String(entityId || "").replace(/_/g, " ")}${window}`;
}

/**
 * The stored result is usually the JSON string the tool returned; a recorder
 * that saw content blocks or an over-cap preview stores something else. Only
 * a parsed envelope is trusted; anything else yields null and the caller
 * falls back to the call's own arguments.
 */
function parseEnvelope(output) {
  const text = typeof output === "string" ? output : null;
  if (text === null) return output && typeof output === "object" && !Array.isArray(output) ? output : null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * `events` are the conversation's stored rows (`{ kind, data }`), in order.
 * Returns `[{ label, ok, error }]`, one per distinct pull, first occurrence
 * wins — the session cache answers a repeat without a network call, and the
 * live pane never listed those either.
 */
export function fetchedFromEvents(events) {
  const calls = new Map();
  for (const ev of events || []) {
    if (ev?.kind === TOOL_USE && ev.data?.name === FETCH_TOOL && ev.data.tool_use_id) {
      calls.set(ev.data.tool_use_id, ev.data.input || {});
    }
  }
  const seen = new Set();
  const rows = [];
  for (const ev of events || []) {
    if (ev?.kind !== TOOL_RESULT || ev.data?.name !== FETCH_TOOL) continue;
    const args = calls.get(ev.data.tool_use_id) || {};
    // The recorder stores the tool's return under `result` (persistence.py's
    // record_tool_result); the first cut of this file read `output`, which
    // never existed, and every reopened pane fell back to the call's
    // arguments with a guessed verdict. The session-audit spin caught it.
    const env = parseEnvelope(ev.data.result);
    const entityId = env?.entity_id || args.entity_id || "";
    const dateFrom = env?.date_from || args.date_from || "";
    const dateTo = env?.date_to || args.date_to || "";
    const key = `${entityId}|${dateFrom}|${dateTo}`;
    if (!entityId || seen.has(key)) continue;
    seen.add(key);
    // Without an envelope the only verdict is the recorder's error flag.
    const ok = env ? env.status === STATUS_OK : !ev.data.is_error;
    rows.push({
      label: fetchLabel(entityId, dateFrom, dateTo),
      ok,
      error: ok ? "" : String(env?.message || ""),
    });
  }
  return rows;
}
