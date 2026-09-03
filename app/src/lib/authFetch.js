"use client";

// Shared fetch helper for user-scoped backend APIs (Bearer JWT + X-API-Key).
// Reads BASE and the API key at call time — the desktop shell repoints both at
// boot (lib/localBackend.js), so callers must never copy them into constants.

import { BASE, backendApiKey } from "./api.js";

/** localStorage key holding the Google Sign-In JWT. */
export const AUTH_TOKEN_KEY = "duct_auth_token";

export function authToken() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(AUTH_TOKEN_KEY) || "";
  } catch {
    return "";
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
