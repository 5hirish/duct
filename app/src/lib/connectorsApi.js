"use client";

// Server-side connector credentials (/api/user/connectors).
//
// Saving a connector here stores its credentials Fernet-encrypted in the
// backend so server-side work — agent-proposed executions, scheduled pulls —
// can run without a browser session. Session-only tokens keep working as
// before; this is the durable layer on top.

import { authedRequest, hasAuthToken } from "./authFetch";

export { hasAuthToken };

/** All stored connector rows for the signed-in user (no secrets returned). */
export function listServerConnectors() {
  return authedRequest("/api/user/connectors");
}

/**
 * Upsert one connector's credentials.
 * `credentials` is the raw dict to encrypt at rest, e.g. `{refresh_token}` or
 * `{refresh_token, developer_token, login_customer_id}` for Google Ads.
 * Note: the blob replaces the stored one whole — always send every field.
 */
export function saveServerConnector({ connector_type, account_id = "", account_name = "", credentials }) {
  return authedRequest("/api/user/connectors", {
    method: "POST",
    body: { connector_type, account_id, account_name, credentials },
  });
}

export function deleteServerConnector(id) {
  return authedRequest(`/api/user/connectors/${id}`, { method: "DELETE" });
}

// --- Per-project connector mappings (/api/user/projects/{id}/connectors) ---
//
// A mapping points one of the project's connector types at one of your saved
// credential rows, so different projects can use different Stripe/ads
// accounts. Without a mapping, agents and reports fall back to your
// account-level connector.

export function listProjectConnectors(projectId) {
  return authedRequest(`/api/user/projects/${encodeURIComponent(projectId)}/connectors`);
}

export function bindProjectConnector(projectId, connectorType, credentialId) {
  return authedRequest(
    `/api/user/projects/${encodeURIComponent(projectId)}/connectors/${encodeURIComponent(connectorType)}`,
    { method: "PUT", body: { connector_credential_id: credentialId } },
  );
}

export function unbindProjectConnector(projectId, connectorType) {
  return authedRequest(
    `/api/user/projects/${encodeURIComponent(projectId)}/connectors/${encodeURIComponent(connectorType)}`,
    { method: "DELETE" },
  );
}

/**
 * Verify manual credentials by listing the accounts they can reach
 * (POST /api/connectors/{id}/accounts). Returns the account rows; throws with
 * the backend's specific message on bad credentials.
 */
export async function listConnectorAccounts(connectorId, credentials) {
  const res = await authedRequest(`/api/connectors/${connectorId}/accounts`, {
    method: "POST",
    body: { credentials },
  });
  return res?.accounts || [];
}
