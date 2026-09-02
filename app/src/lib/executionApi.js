"use client";

// Staged-execution client (/api/execute) — the two-phase-commit review flow:
// an agent proposes a change set, the user approves it here, apply performs
// the mutations with per-change results and rollback handles.
//
// Authenticated with the Bearer JWT (localStorage "duct_auth_token") plus the
// shared X-API-Key, same as projectsApi.js. Apply/rollback/propose carry the
// BYO connector credentials per request (sessionStorage / keychain); when a
// field is empty the backend falls back to the user's stored encrypted
// connector credentials (saved from /connections), then server env.

import { BASE } from "./api";
import { authedHeaders } from "./authFetch";
import { googleAdsByoCredentials } from "./adsCredentials";

function authHeaders(extra = {}) {
  return authedHeaders(extra);
}

async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(`${BASE}/api/execute${path}`, {
    method,
    headers: authHeaders(body !== undefined ? { "Content-Type": "application/json" } : {}),
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

/**
 * BYO credentials for the change set's connector, from session/keychain
 * storage. Empty fields are fine: the backend falls back to the user's stored
 * (encrypted) connector credentials, then server env.
 */
export async function executionCredentials(connectorType) {
  if (connectorType === "ga4") {
    return { refresh_token: sessionStorage.getItem("ga4_refresh_token") || "" };
  }
  if (connectorType === "gtm") {
    return { refresh_token: sessionStorage.getItem("gtm_refresh_token") || "" };
  }
  if (connectorType !== "google_ads") {
    // Manual-credential connectors (Mixpanel …) have no browser token — the
    // backend resolves their stored encrypted rows.
    return {};
  }
  const ads = await googleAdsByoCredentials();
  return {
    refresh_token: sessionStorage.getItem("gads_refresh_token") || "",
    developer_token: ads.developer_token,
    login_customer_id: ads.login_customer_id,
  };
}

export function listChangeSets() {
  return request("");
}

export function getChangeSet(id) {
  return request(`/${id}`);
}

export function listOps() {
  return request("/ops");
}

export async function proposeChangeSet(changeSet) {
  const credentials = await executionCredentials(changeSet.connector_type);
  return request("", { method: "POST", body: { ...changeSet, credentials } });
}

export function approveChangeSet(id, changeIds = null) {
  return request(`/${id}/approve`, { method: "POST", body: { change_ids: changeIds } });
}

export function rejectChangeSet(id) {
  return request(`/${id}/reject`, { method: "POST" });
}

export async function applyChangeSet(id, connectorType) {
  const credentials = await executionCredentials(connectorType);
  return request(`/${id}/apply`, { method: "POST", body: { credentials } });
}

export async function rollbackChangeSet(id, connectorType) {
  const credentials = await executionCredentials(connectorType);
  return request(`/${id}/rollback`, { method: "POST", body: { credentials } });
}

export function listGuardrails(connectorType = "", accountId = "") {
  const params = new URLSearchParams();
  if (connectorType) params.set("connector_type", connectorType);
  if (accountId) params.set("account_id", accountId);
  const qs = params.toString();
  return request(`/guardrails${qs ? `?${qs}` : ""}`);
}

export function createGuardrail(guardrail) {
  return request("/guardrails", { method: "POST", body: guardrail });
}

export function deleteGuardrail(id) {
  return request(`/guardrails/${id}`, { method: "DELETE" });
}
