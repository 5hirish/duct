"use client";

// Shared fetch helper for user-scoped backend APIs (Bearer JWT + X-API-Key).
// Reads BASE and the API key at call time — the desktop shell repoints both at
// boot (lib/localBackend.js), so callers must never copy them into constants.
//
// This module also owns what a 401 *means*, so that answer lives in one place
// rather than being re-decided per page. See `endSession`.

import { BASE, backendApiKey } from "./api.js";
import { isDesktopShell } from "./shell.js";

/** localStorage key holding the Google Sign-In JWT, in a browser. */
export const AUTH_TOKEN_KEY = "duct_auth_token";
/**
 * The desktop shell's own key. Same storage, deliberately different name.
 *
 * The dev shell loads `http://localhost:3003` and the production shell loads
 * `https://app.getduct.ai` — in both cases *the same origin a browser uses*,
 * so the shell and a browser tab are co-tenants of one `localStorage`. But the
 * shell repoints every API call at its bundled sidecar (`localBackend.js`),
 * which is a different server, with its own SQLite database and its own
 * per-install JWT secret (`backend/local_server.py`). Sharing one key across
 * those meant whichever signed in last overwrote the other's session, and the
 * damage landed on the *next* request rather than at sign-in: the token
 * verified or not depending on whether the two secrets happened to agree, so
 * the same root cause surfaced as either "Invalid token" or "User not found"
 * — a session naming a user that backend's database has never seen. Connecting
 * a data source is where it was usually noticed, because that is the first
 * thing that must be written server-side to be worth anything.
 *
 * Keyed on `isDesktopShell()` rather than on the backend URL because the
 * sidecar binds port 0 and gets a new port every launch, so the URL is not a
 * stable identity; and rather than on a `getShellInfo()` capability — which is
 * this file's usual rule — because that rule exists to keep old shells on the
 * plain web path, and here there is no feature to degrade. Partitioning is
 * total on purpose: a shell too old to run a sidecar keeps its own copy of a
 * hosted session, which is self-consistent and still cannot collide.
 */
export const DESKTOP_AUTH_TOKEN_KEY = "duct_auth_token__desktop";

/**
 * sessionStorage key naming where to land once signed in. The invite page and
 * `endSession` both park a path here; the sign-in page consumes it and honours
 * same-origin paths only, so a parked value can never become an open redirect.
 */
export const POST_SIGNIN_REDIRECT_KEY = "duct_post_signin_redirect";

/** sessionStorage flag: the user was sent to sign-in, they did not choose it. */
export const SIGNIN_REASON_KEY = "duct_signin_reason";
export const SIGNIN_REASON_EXPIRED = "expired";

/** Fired on `window` when the backend refuses the session; AuthProvider signs out. */
export const SESSION_EXPIRED_EVENT = "duct:session-expired";

/** Which key this shell owns. The web key is unchanged, so no browser session is lost. */
export function authTokenKey() {
  return isDesktopShell() ? DESKTOP_AUTH_TOKEN_KEY : AUTH_TOKEN_KEY;
}

export function authToken() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(authTokenKey()) || "";
  } catch {
    return "";
  }
}

/** Persist a freshly minted session token for this shell. */
export function setAuthToken(token) {
  // Signing in is what re-arms `endSession`. Its once-only guard is per page
  // load, and sign-in is a soft navigation: without this, a session that goes
  // bad after a re-login would be the one 401 nobody acts on.
  sessionEnded = false;
  try {
    window.localStorage.setItem(authTokenKey(), token);
  } catch {
    /* private mode / storage disabled — the session lasts this page load */
  }
}

export function clearAuthToken() {
  try {
    window.localStorage.removeItem(authTokenKey());
  } catch {
    /* nothing stored is the state we wanted anyway */
  }
}

export function hasAuthToken() {
  return Boolean(authToken());
}

/** Claims from a JWT without verifying it — display only, never a trust decision. */
export function decodeJwtPayload(token) {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

/** True when `token` parses and its `exp` is still in the future. */
export function isTokenValid(token) {
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  if (!payload || !payload.exp) return false;
  return payload.exp * 1000 > Date.now();
}

export function authedHeaders(extra = {}) {
  const headers = { ...extra };
  const apiKey = backendApiKey();
  if (apiKey) headers["X-API-Key"] = apiKey;
  const token = authToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

/**
 * The backend refused our identity. Pages must not render this as copy: the
 * user is already on their way to sign-in, and a red string where their empty
 * state belongs is both wrong and the least useful thing to show them. Test
 * for it with `isSessionExpired` rather than matching on the message.
 */
export class SessionExpiredError extends Error {
  constructor(detail, status) {
    super(detail || "Your session has ended.");
    this.name = "SessionExpiredError";
    this.sessionExpired = true;
    this.status = status;
  }
}

/** True for the error a 401 raises once the session has been retired. */
export function isSessionExpired(err) {
  return Boolean(err && err.sessionExpired);
}

// One 401 is enough. A page that loads four panels in parallel gets four of
// them, and each would otherwise re-park the redirect and re-dispatch.
let sessionEnded = false;

/**
 * Retire a session the backend has already refused.
 *
 * 401 is never ambiguous here: the shared X-API-Key fails with 403, so a 401
 * always means the *user* half of the credential is bad — missing, expired, or
 * (the case this was written for) well-formed, correctly signed and unexpired,
 * naming a user the answering backend's database has never seen, which the API
 * words as "User not found". `AuthGuard` cannot see any of that: it checks
 * `exp` on a token it never verifies against a server. Without this the app
 * stays convinced it is signed in and every user-scoped page paints the
 * backend's 401 detail where its own empty state belongs.
 *
 * The token goes through `clearAuthToken`, not a hardcoded key: the desktop
 * shell stores its session under a different name (see DESKTOP_AUTH_TOKEN_KEY)
 * and removing the browser's would leave the offending token in place.
 */
function endSession() {
  if (sessionEnded || typeof window === "undefined") return;
  sessionEnded = true;
  clearAuthToken();
  try {
    window.sessionStorage.setItem(
      POST_SIGNIN_REDIRECT_KEY,
      window.location.pathname + window.location.search
    );
    window.sessionStorage.setItem(SIGNIN_REASON_KEY, SIGNIN_REASON_EXPIRED);
  } catch {
    /* Storage can be denied (private mode); the sign-out below still happens. */
  }
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
}

/**
 * Retire the session when `res` is a 401. Returns true when it did.
 *
 * Exported for the callers that deliberately degrade instead of throwing — the
 * project list falls back to its local cache rather than emptying the sidebar
 * — so a dead session still ends even where its response is swallowed.
 */
export function endSessionIfUnauthorized(res) {
  if (res.status !== 401) return false;
  endSession();
  return true;
}

/** Backend error detail, or a status-shaped fallback when the body is not ours. */
async function errorDetail(res) {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string" && body.detail) return body.detail;
  } catch {
    /* non-JSON error body */
  }
  return `Server error ${res.status}`;
}

/**
 * Always throws. Callers get `error.status` either way: a 401 means the stored
 * session no longer resolves to a user on THIS backend, which is a different
 * problem from the request being wrong and has a different fix.
 *
 * `retireSession` is how a caller opts out of the automatic sign-out. The
 * connections page does, and is the reason the flag exists: its 401 lands the
 * moment the user returns from Google, where bouncing them to sign-in would
 * discard the connection they just approved. It explains instead.
 */
export async function throwForStatus(res, { retireSession = true } = {}) {
  const detail = await errorDetail(res);
  if (retireSession && endSessionIfUnauthorized(res)) {
    throw new SessionExpiredError(detail, res.status);
  }
  const error = new Error(detail);
  error.status = res.status;
  throw error;
}

/**
 * `fetch` against the backend with auth headers attached and failures funnelled
 * through `throwForStatus`. Returns the raw Response — for callers that want
 * bytes (artifact downloads) rather than JSON.
 */
export async function authedFetch(path, { method = "GET", body, headers, retireSession } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: authedHeaders({
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) await throwForStatus(res, { retireSession });
  return res;
}

/** JSON request against the backend; throws Error(detail) on non-2xx. */
export async function authedRequest(path, { method = "GET", body, retireSession } = {}) {
  const res = await authedFetch(path, { method, body, retireSession });
  return res.status === 204 ? null : res.json();
}
