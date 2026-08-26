"use client";

// Shared fetch helper for user-scoped backend APIs (Bearer JWT + X-API-Key).
// Reads BASE and the API key at call time — the desktop shell repoints both at
// boot (lib/localBackend.js), so callers must never copy them into constants.

import { BASE, backendApiKey } from "./api";

const TOKEN_KEY = "duct_auth_token";

export function authToken() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function hasAuthToken() {
  return Boolean(authToken());
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
    throw new Error(detail || `Server error ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}
