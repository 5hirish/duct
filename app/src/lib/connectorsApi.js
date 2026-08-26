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
