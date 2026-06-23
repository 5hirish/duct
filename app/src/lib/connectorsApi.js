"use client";

// User-scoped connector credentials against the backend (/api/user/connectors).
//
// Authenticated with the Bearer JWT minted by Google Sign-In (localStorage
// "duct_auth_token") + the shared X-API-Key — same pattern as projectsApi.js.
// Credentials are encrypted at rest server-side and read back only by the
// backend (e.g. service/higgsfield/auth resolves the Higgsfield token here for
// the headless content runner). This API only ever exposes metadata, never the
// secret itself.

import { BASE } from "./api";

const TOKEN_KEY = "duct_auth_token";

function authToken() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  const apiKey = process.env.NEXT_PUBLIC_DUCT_API_KEY;
  if (apiKey) headers["X-API-Key"] = apiKey;
  const token = authToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

/** List the current user's connector credentials (metadata only — no secrets). */
export async function listConnectors() {
  if (!authToken()) return [];
  const res = await fetch(`${BASE}/api/user/connectors`, { headers: authHeaders() });
  if (!res.ok) throw new Error((await res.text()) || `Server error ${res.status}`);
  return res.json();
}

/**
 * Upsert a connector credential. `credentials` is a raw dict encrypted at rest.
 * For Higgsfield: { connector_type: "higgsfield", credentials: { api_token } }.
 */
export async function saveConnector({ connectorType, accountId = "", accountName = "", credentials }) {
  const res = await fetch(`${BASE}/api/user/connectors`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      connector_type: connectorType,
      account_id: accountId,
      account_name: accountName,
      credentials,
    }),
  });
  if (!res.ok) throw new Error((await res.text()) || `Server error ${res.status}`);
  return res.json();
}

/** Delete a connector credential by id. */
export async function deleteConnector(id) {
  const res = await fetch(`${BASE}/api/user/connectors/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok && res.status !== 204) {
    throw new Error((await res.text()) || `Server error ${res.status}`);
  }
}
