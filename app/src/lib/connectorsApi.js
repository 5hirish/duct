"use client";

// Server-side connector credentials (/api/user/connectors).
//
// Saving a connector here stores its credentials Fernet-encrypted in the
// backend so server-side work — agent-proposed executions, scheduled pulls —
// can run without a browser session. Session-only tokens keep working as
// before; this is the durable layer on top.

import { authedRequest, hasAuthToken } from "./authFetch";
import { SESSION_TOKEN_KEYS, resolveConnectedTypes } from "./connectorCount";
import { connectedCount } from "./dataSources";

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
export async function saveServerConnector({
  connector_type,
  account_id = "",
  account_name = "",
  credentials,
  // Space-separated scopes the provider actually granted, straight from the
  // OAuth round-trip. Omit it and the server keeps whatever it already
  // recorded — a rename or a manual re-save must not erase the real grant.
  granted_scopes = "",
}) {
  const res = await authedRequest("/api/user/connectors", {
    method: "POST",
    body: { connector_type, account_id, account_name, credentials, granted_scopes },
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

/**
 * How many data sources are actually reachable — the one answer, for every
 * surface that shows a count.
 *
 * This lived in `deskApi.js` and the sidebar badge had its own, older answer
 * (`connectedConnectorTypes` alone), so the two contradicted each other on
 * screen: the badge read "1" from a session-only Google token while the desk
 * checklist, asking the server, correctly said no source was connected. Both
 * were reporting honestly about different questions, which is the worst
 * version of this bug — neither looks broken on its own.
 *
 * The server answer wins because it is the one that matches what a run can
 * actually use: it walks the whole registry, so a pasted API key counts like
 * an OAuth grant, and it applies the project's bindings. The browser's own
 * view is kept strictly as a fallback — signed out, offline, or against a
 * backend without the route, this tab may still hold session-only tokens, and
 * answering "zero" then is its own lie.
 */
export async function countConnectedSources(projectId) {
  let rows = null;
  try {
    rows = await (projectId ? listProjectDataSources(projectId) : listAccountDataSources());
  } catch {
    /* fall through to the browser's own view */
  }
  if (Array.isArray(rows)) return connectedCount(rows);
  try {
    return (await connectedConnectorTypes())?.size ?? 0;
  } catch {
    return 0;
  }
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

export function bindProjectConnector(
  projectId,
  connectorType,
  credentialId,
  { entityId = "", entityName = "" } = {},
) {
  return authedRequest(
    `/api/user/projects/${encodeURIComponent(projectId)}/connectors/${encodeURIComponent(connectorType)}`,
    {
      method: "PUT",
      body: {
        connector_credential_id: credentialId,
        entity_id: entityId,
        entity_name: entityName,
      },
    },
  );
}

/**
 * What a saved connector can actually read — Search Console properties, GA4
 * properties, Tag Manager containers.
 *
 * Server-side credential resolution on purpose: the browser holds no refresh
 * token for an OAuth connector and must not be handed one to render a list.
 * Returns `{ entities, supported, entity_noun, entity_noun_plural }`; the nouns
 * come back even when nothing is selectable, because the label is still needed.
 */
export function listConnectorEntities(rowId) {
  return authedRequest(`/api/user/connectors/${encodeURIComponent(rowId)}/entities`);
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
