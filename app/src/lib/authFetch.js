"use client";

// Shared fetch helper for user-scoped backend APIs (Bearer JWT + X-API-Key).
// Reads BASE and the API key at call time — the desktop shell repoints both at
// boot (lib/localBackend.js), so callers must never copy them into constants.

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

/** JSON request against the backend; throws Error(detail) on non-2xx. */
export async function authedRequest(path, { method = "GET", body } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: authedHeaders(body !== undefined ? { "Content-Type": "application/json" } : {}),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail || "";
    } catch {
      /* non-JSON error body */
    }
    const error = new Error(detail || `Server error ${res.status}`);
    // Callers need the status, not just the message: a 401 here means the
    // stored session no longer resolves to a user on THIS backend, which is a
    // different problem from the request being wrong, and has a different fix.
    error.status = res.status;
    throw error;
  }
  return res.status === 204 ? null : res.json();
}
