"use client";

// Staged-execution client (/api/execute) — the two-phase-commit review flow:
// an agent proposes a change set, the user approves it here, apply performs
// the mutations with per-change results and rollback handles.
//
// Authenticated with the Bearer JWT (localStorage "duct_auth_token") plus the
// shared X-API-Key, same as projectsApi.js. No call carries connector
// credentials: the backend resolves the project's binding, then the user's
// stored connection, then server env — the same ladder an agent's apply uses,
// so a change applied here can be rolled back from anywhere.

import { authedRequest } from "./authFetch";
import { trackEvent, AnalyticsEvent } from "./analytics";

function request(path, options) {
  return authedRequest(`/api/execute${path}`, options);
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

export function proposeChangeSet(changeSet) {
  return request("", { method: "POST", body: changeSet });
}

export async function approveChangeSet(id, changeIds = null) {
  const result = await request(`/${id}/approve`, { method: "POST", body: { change_ids: changeIds } });
  // Here rather than at the two call sites, so approving from the change-set
  // card and from the execute page are one event — and only after the server
  // took it, because an approval that failed is not an approval.
  trackEvent(AnalyticsEvent.ExecutionApproved, { kind: result?.connector_type || "" });
  return result;
}

export function rejectChangeSet(id) {
  return request(`/${id}/reject`, { method: "POST" });
}

export function applyChangeSet(id) {
  return request(`/${id}/apply`, { method: "POST" });
}

export function rollbackChangeSet(id) {
  return request(`/${id}/rollback`, { method: "POST" });
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
