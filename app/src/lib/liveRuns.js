/**
 * The runs this tab left behind on purpose.
 *
 * Leaving a workspace mid-run used to delete the session, so opening
 * Connections halfway through a brief killed the brief. Now the hook detaches
 * instead (hooks/useAgentSession.js): the stream closes, the page keeps its
 * reload handle, and the run is noted here so the sidebar can say the agent
 * is still working. The entry goes when the page reattaches, when Stop is
 * pressed, or when hooks/useLiveRuns.js hears from the backend that the turn
 * is over.
 *
 * sessionStorage, like the reload handle: per tab, gone with the tab, every
 * access guarded because a private window may throw on the accessor itself.
 * Readers get the same array until something changes, which is what
 * useSyncExternalStore needs to avoid a render loop.
 */

const KEY = "duct:live_runs";
const EMPTY = Object.freeze([]);

/** Where each agent's workspace lives, so a run can light its sidebar entry. */
const ROUTE_FOR_AGENT = Object.freeze({
  insights: "/insights",
  audit_seo: "/audit",
  tiktok_studio: "/content",
});

let snapshot = null;
const listeners = new Set();

function read() {
  try {
    const raw = sessionStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((r) => r && typeof r.sessionId === "string") : [];
  } catch {
    return [];
  }
}

function write(next) {
  snapshot = next.length ? Object.freeze(next) : EMPTY;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable — the badge lives for this page only */
  }
  for (const listener of listeners) listener();
}

export function listDetachedRuns() {
  if (snapshot === null) {
    const runs = read();
    snapshot = runs.length ? Object.freeze(runs) : EMPTY;
  }
  return snapshot;
}

export function rememberDetachedRun({ agentType, sessionId, conversationId = null, handleKey = "" }) {
  if (!sessionId) return;
  const rest = listDetachedRuns().filter((r) => r.sessionId !== sessionId);
  write([...rest, { agentType, sessionId, conversationId, handleKey, at: Date.now() }]);
}

export function forgetDetachedRun(sessionId) {
  if (!sessionId) return;
  const current = listDetachedRuns();
  const next = current.filter((r) => r.sessionId !== sessionId);
  if (next.length !== current.length) write(next);
}

export function subscribeDetachedRuns(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The runs whose workspace sits under a sidebar entry's route prefix. */
export function runsUnder(runs, matchPrefix) {
  if (!matchPrefix) return EMPTY;
  return runs.filter((r) => {
    const route = ROUTE_FOR_AGENT[r.agentType];
    return Boolean(route) && (matchPrefix === route || matchPrefix.startsWith(route + "/"));
  });
}

/** Test seam: forget the cached snapshot so the next read hits storage. */
export function _resetDetachedRunsForTests() {
  snapshot = null;
  listeners.clear();
}
