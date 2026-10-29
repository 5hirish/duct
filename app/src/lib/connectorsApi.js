"use client";

// Server-side connector credentials (/api/user/connectors).
//
// The only place a connection lives. Credentials are stored Fernet-encrypted
// in the backend, so every tab, browser and the desktop app see the same
// connections, and server-side work — agent-proposed executions, scheduled
// pulls — runs without a browser. A sign-in connector's token never comes to
// this app at all: the page mints a connect link, the provider's grant is
// parked on the server, and the same session claims it (issue #456).

import { authedRequest, hasAuthToken } from "./authFetch";
import { resolveConnectedTypes } from "./connectorCount";
import { connectedCount } from "./dataSources";

export { hasAuthToken };

/** All stored connector rows for the signed-in user (no secrets returned). */
export function listServerConnectors() {
  return authedRequest("/api/user/connectors");
}

/**
 * Upsert one pasted-key connector's credentials (Stripe, Meta, a GitHub
 * token, …). `credentials` is the raw dict to encrypt at rest, and replaces
 * the stored one whole — always send every field. A sign-in connector's token
 * is refused here; it is only ever written by `claimConnectorGrant`.
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
    // A 401 here would sign the person out mid-form and throw away the keys
    // they just pasted; the card shows the error instead.
    retireSession: false,
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

/**
 * Change a stored connection's non-secret settings (the row's `settings`),
 * e.g. `{ login_customer_id }` for the Google Ads manager account. Merged on
 * the server: the token stays where the connect flow put it. An empty value
 * clears a setting. Resolves to the updated row.
 */
export function updateConnectorSettings(id, settings) {
  return authedRequest(`/api/user/connectors/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: { settings },
  });
}

// --- Connecting by signing in (Google, GitHub) -------------------------------
//
// The flow lives in backend/routes/auth.py. What the browser does: mint a
// single-use link naming the signed-in user, open the authorize route with it
// (lib/connectorAuth.js), and — when the provider hands back a code — claim
// the grant with the same session. The claim is the only way a sign-in
// connector's credential is saved; saveServerConnector refuses one.

/** A five-minute, single-use code for `/auth/connectors/{type}/oauth/authorize?link=`. */
export async function startConnectLink(connectorType) {
  const res = await authedRequest("/api/user/connectors/connect-link", {
    method: "POST",
    body: { connector_type: connectorType },
  });
  return res?.link || "";
}

/**
 * Save a Google connector's grant to the account. Resolves to the stored row
 * (never a token); rejects when the code expired or belongs to a connect
 * another account started.
 */
export async function claimConnectorGrant(code) {
  const res = await authedRequest("/api/user/connectors/claim", {
    method: "POST",
    // This lands the instant the user returns from Google, and a sign-in
    // bounce here would discard the connection they just approved.
    retireSession: false,
    body: { code },
  });
  notifyConnectorsChanged();
  return res;
}

// --- "how many sources are live?" ------------------------------------------
//
// Asked by the sidebar badge, and answered from the place the Connections
// page reads: the stored rows. Counting DISTINCT connector types — two Stripe
// accounts are one connected source, not two, which is what the Connections
// page shows and therefore what the badge has to agree with.

/** Fired whenever connector state changes, so anything showing a count can
 *  re-read it. `storage` events do not cover this: a write to the server
 *  fires none. */
export { resolveConnectedTypes } from "./connectorCount";

export const CONNECTORS_CHANGED = "duct:connectors-changed";

export function notifyConnectorsChanged() {
  sourceCountCache.clear();
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CONNECTORS_CHANGED));
}

/** Connector types with a stored credential, as a Set. Never throws — a
 *  signed-out or offline caller gets the empty set. */
export async function connectedConnectorTypes() {
  const serverTypes = [];
  if (hasAuthToken()) {
    try {
      for (const row of (await listServerConnectors()) || []) {
        if (row?.connector_type) serverTypes.push(row.connector_type);
      }
    } catch {
      /* offline / signed-out — nothing this tab can vouch for */
    }
  }
  return resolveConnectedTypes({ serverTypes });
}

// --- The inventory: what can this project actually reach? ----------------
//
// Server-resolved, so it covers every connector in the registry — OAuth and
// pasted-API-key alike — and applies the project's bindings. Prefer these over
// connectedConnectorTypes() wherever a project id is available: that function
// sees only the stored rows, and knows nothing about which account a project
// has chosen.
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
 * The inventory answer wins because it is the one that matches what a run can
 * actually use: it walks the whole registry, so a pasted API key counts like
 * an OAuth grant, and it applies the project's bindings. The plain row count
 * is kept as the fallback for a backend without the inventory route.
 */
export async function countConnectedSources(projectId) {
  const key = projectId || "";
  const hit = sourceCountCache.get(key);
  if (hit && Date.now() - hit.at < SOURCE_COUNT_TTL_MS) return hit.promise;
  const promise = countConnectedSourcesUncached(projectId);
  sourceCountCache.set(key, { at: Date.now(), promise });
  return promise;
}

// The sidebar badge asks on mount, focus, every project switch and every
// cross-tab storage write; the desk asks on open, on visibility and every 30
// seconds while a thread runs. Same question, same project, answered by a
// server round trip each time — 47 of them in one evening's session, at a
// median 2.3 s against a remote database. One answer per project per TTL,
// in-flight calls shared, and `notifyConnectorsChanged` drops the cache so
// a connection made a second ago is not hidden behind it.
const SOURCE_COUNT_TTL_MS = 20_000;
const sourceCountCache = new Map();

async function countConnectedSourcesUncached(projectId) {
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

// --- GitHub App: the one-click GitHub connection ----------------------------
//
// The flow lives in backend/service/github/app.py and starts like a Google
// connect (`startConnectorOAuth("github")`). Two differences: ask first
// whether this server has an App (self-hosted ones do not, and keep the token
// form), and claim with the GitHub route, which stores a row per repository.

/** `{ available, manage_url }` — whether GitHub connects in one click here. */
export function getGitHubApp() {
  return authedRequest("/api/user/connectors/github/app");
}

/**
 * Save what GitHub granted: one row per repository. Resolves to
 * `{ connectors, omitted }`; rejects when the code expired or belongs to a
 * connect another account started.
 */
export async function claimGitHubGrant(code) {
  const res = await authedRequest("/api/user/connectors/github/claim", {
    method: "POST",
    // Same reason as saveServerConnector: this lands the instant the user
    // returns from GitHub, and a sign-in bounce would discard the connect.
    retireSession: false,
    body: { code },
  });
  notifyConnectorsChanged();
  return res;
}

// --- MCP servers the user connects (/api/user/mcp) --------------------------
//
// The flow lives in backend/routes/mcp_servers.py. A connect answers one of
// three ways: saved on the spot (a key, or a server that needs no sign-in),
// a vendor sign-in to send the person to, or a request for a key because the
// server offers no sign-in Duct can start. A sign-in comes back as a grant
// that only this signed-in session can claim, the GitHub shape.

/** Where an MCP sign-in comes home: `/connections?connector=mcp&…`. */
export const MCP_CONNECTOR = "mcp";

/** What `POST /api/user/mcp/servers` answers. */
export const McpConnect = Object.freeze({
  CONNECTED: "connected",
  AUTHORIZE: "authorize",
  NEEDS_KEY: "needs_key",
});

/** How a connected server signs in (`auth` on each server row). */
export const McpAuth = Object.freeze({
  OAUTH: "oauth",
  KEY: "key",
  NONE: "none",
});

/** A server row's `status`. */
export const McpServerStatus = Object.freeze({
  CONNECTED: "connected",
  NEEDS_REAUTH: "needs_reauth",
});

/** `error=` on the sign-in's return, coarse on purpose (it is in the URL). */
export const McpReturnError = Object.freeze({
  EXPIRED: "expired",
  CONSENT: "consent",
  EXCHANGE: "exchange",
});

/** `[{ id, label, url, home, key_url }]` — the servers offered by name. */
export async function listMcpPresets() {
  const res = await authedRequest("/api/user/mcp/presets");
  return res?.presets || [];
}

/** The user's connected servers. No secret comes back. */
export async function listMcpServers() {
  const res = await authedRequest("/api/user/mcp/servers");
  return res?.servers || [];
}

/**
 * Start (or finish, with a key) connecting one server. Pass `preset` for a
 * named one or `url` for any other. Resolves to `{ status, server }`,
 * `{ status, authorize_url }` or `{ status, message }` — see `McpConnect`.
 *
 * A refused key is a 422 and an unreachable server a 502; neither is about
 * the Duct session, so neither may sign the person out. `client: "desktop"`
 * sends the sign-in home through the shell's relay page instead of this tab.
 */
export function connectMcpServer({ url = "", preset = "", name = "", apiKey = "", client = "" }) {
  return authedRequest("/api/user/mcp/servers", {
    method: "POST",
    retireSession: false,
    body: { url, preset, name, api_key: apiKey, client },
  });
}

/** Save a finished sign-in. Rejects (404) when it expired or another account started it. */
export async function claimMcpServer(code) {
  const res = await authedRequest("/api/user/mcp/claim", {
    method: "POST",
    // Lands the instant the person returns from the vendor, like the GitHub
    // claim: a sign-in bounce here would throw away the sign-in they just did.
    retireSession: false,
    body: { code },
  });
  return res?.server || null;
}

export function deleteMcpServer(id) {
  return authedRequest(`/api/user/mcp/servers/${encodeURIComponent(id)}`, { method: "DELETE" });
}
