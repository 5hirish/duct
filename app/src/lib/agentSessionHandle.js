/**
 * Where a tab remembers which agent session it was attached to.
 *
 * A reload used to start the run over — the session id lived in a ref and
 * died with the component, so the new mount could only create. The backend
 * keeps a run alive for a grace window after its stream drops and its
 * conversation forever, which means a reload can pick up exactly where it was:
 * reattach to the live session if it is still there, resume the conversation
 * if it is not.
 *
 * sessionStorage on purpose. It is per tab, so a second tab is a second
 * session, and it dies with the tab, so "the previous run" cannot leak into
 * tomorrow. Every read and write is guarded: a private window or an embedded
 * webview may throw on the accessor itself.
 */

const PREFIX = "duct:agent_session:";

export function readSessionHandle(key) {
  if (!key) return null;
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function writeSessionHandle(key, { sessionId, conversationId }) {
  if (!key) return;
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify({ sessionId, conversationId, at: Date.now() }));
  } catch {
    /* storage unavailable — the reload falls back to a fresh open */
  }
}

export function clearSessionHandle(key) {
  if (!key) return;
  try {
    sessionStorage.removeItem(PREFIX + key);
  } catch {
    /* ignore */
  }
}
