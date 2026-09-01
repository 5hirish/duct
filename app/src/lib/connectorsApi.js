"use client";

// Server-side connector credentials (/api/user/connectors).
//
// Saving a connector here stores its credentials Fernet-encrypted in the
// backend so server-side work — agent-proposed executions, scheduled pulls —
// can run without a browser session. Session-only tokens keep working as
// before; this is the durable layer on top.

import { authedRequest, hasAuthToken } from "./authFetch";
import { SESSION_TOKEN_KEYS, resolveConnectedTypes } from "./connectorCount";

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
export async function saveServerConnector({ connector_type, account_id = "", account_name = "", credentials }) {
  const res = await authedRequest("/api/user/connectors", {
    method: "POST",
    body: { connector_type, account_id, account_name, credentials },
  });
  notifyConnectorsChanged();
  return res;
}

export async function deleteServerConnector(id) {
  const res = await authedRequest(`/api/user/connectors/${id}`, { method: "DELETE" });
  notifyConnectorsChanged();
  return res;
}

// --- "how many sources are live?" ------------------------------------------
//
// Asked by the sidebar badge, and answered from the same two places the
// Connections page reads: the durable server rows, plus the session-only OAuth
// tokens a signed-out user can still hold. Counting DISTINCT connector types —
// two Stripe accounts are one connected source, not two, which is what the
// Connections page shows and therefore what the badge has to agree with.

/** Fired whenever connector state changes, so anything showing a count can
 *  re-read it. `storage` events do not cover this: sessionStorage is per-tab
 *  and same-tab writes never fire one. */
export { resolveConnectedTypes } from "./connectorCount";

export const CONNECTORS_CHANGED = "duct:connectors-changed";

export function notifyConnectorsChanged() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CONNECTORS_CHANGED));
}

/** Connector types with credentials somewhere, as a Set. Never throws — a
 *  signed-out or offline caller still gets the session-only answer. */
export async function connectedConnectorTypes() {
  const sessionTypes = [];
  if (typeof window !== "undefined") {
    for (const [type, key] of Object.entries(SESSION_TOKEN_KEYS)) {
      try {
        if (sessionStorage.getItem(key)) sessionTypes.push(type);
      } catch {
        /* storage disabled — server rows below still count */
      }
    }
  }

  const serverTypes = [];
  if (hasAuthToken()) {
    try {
      for (const row of (await listServerConnectors()) || []) {
        if (row?.connector_type) serverTypes.push(row.connector_type);
      }
    } catch {
      /* offline / signed-out — the session-only answer stands */
    }
  }

  let hasAdsDevToken = false;
  if (sessionTypes.includes("google_ads") || serverTypes.includes("google_ads")) {
    const { getAdsDeveloperToken } = await import("./adsCredentials");
    hasAdsDevToken = !!(await getAdsDeveloperToken());
  }
  return resolveConnectedTypes({ sessionTypes, serverTypes, hasAdsDevToken });
}

// --- The inventory: what can this project actually reach? ----------------
//
// Server-resolved, so it covers every connector in the registry — OAuth and
// pasted-API-key alike — and applies the project's bindings. Prefer these over
// connectedConnectorTypes() wherever a project id is available: that function
// can only see the four Google session-token keys plus stored rows, and knows
// nothing about which account a project has chosen.
//
// Each row: {connector_id, label, status, account_id, account_name,
//            auth_kind, has_catalog, catalog_stale, stored_accounts}
// See lib/dataSources.js for what the statuses mean.

/** Inventory for one project — bindings applied. */
export function listProjectDataSources(projectId) {
  return authedRequest(
    `/api/user/projects/${encodeURIComponent(projectId)}/data-sources`
  );
}

/** Inventory for the account, for before a project exists. */
export function listAccountDataSources() {
  return authedRequest("/api/user/connectors/data-sources");
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
