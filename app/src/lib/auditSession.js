"use client";

/**
 * The hand-off between whoever starts an audit and the page that runs it.
 *
 * The params travel through `sessionStorage` rather than the URL because they
 * carry a whole request body. Two kinds of thing live in there and they must
 * not mix: the **request**, which goes to the backend verbatim and where an
 * unknown field is a 422, and the **client** state, which only the session
 * page reads — whether to show the "connect a model" card first, whether the
 * conversation should open with a message, which project this run is writing
 * to.
 *
 * That separation used to be three ad-hoc keys stripped by name on arrival,
 * and each new one meant editing the strip list in a file that had no other
 * reason to change. Nesting them under one key means the request is whatever
 * is left, so a fourth costs nothing and cannot leak into the body.
 */

const PREFIX = "audit_session_";
const CLIENT_KEY = "client";

/** How a run relates to the project it writes to. */
export const PROJECT_NEW = "new";
export const PROJECT_EXISTING = "existing";

/** Store one audit's params and return the id that addresses them. */
export function openAuditSession(request, client = {}) {
  const sessionId = crypto.randomUUID();
  writeAuditSession(sessionId, request, client);
  return sessionId;
}

/** Overwrite one audit's params — used to spend a once-only client field. */
export function writeAuditSession(sessionId, request, client = {}) {
  const payload = { ...request };
  const kept = Object.fromEntries(Object.entries(client).filter(([, v]) => v));
  if (Object.keys(kept).length) payload[CLIENT_KEY] = kept;
  try {
    sessionStorage.setItem(`${PREFIX}${sessionId}`, JSON.stringify(payload));
  } catch {
    /* private mode: the session page will send the user back to /audit/seo */
  }
}

/**
 * `{ request, client }` for a stored audit, or null when there is nothing to
 * resume — a reload of a link someone kept, or storage that was cleared.
 */
export function readAuditSession(sessionId) {
  let raw = null;
  try {
    raw = sessionStorage.getItem(`${PREFIX}${sessionId}`);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const { [CLIENT_KEY]: client, ...request } = JSON.parse(raw);
    return { request, client: client || {} };
  } catch {
    return null;
  }
}
