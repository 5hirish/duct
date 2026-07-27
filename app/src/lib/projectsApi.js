"use client";

// User-scoped project persistence against the backend (/api/user/projects).
//
// These endpoints are authenticated with the Bearer JWT minted by Google
// Sign-In (stored in localStorage under "duct_auth_token"). We also forward
// the shared X-API-Key for consistency with the rest of the app's calls.
//
// localStorage is the offline cache / source for the synchronous API in
// lib/projects.js; these functions write through to / read from the server in
// the background. Every call is a no-op (returns null/[]) when no valid token
// is present, so signed-out or token-less sessions degrade to local-only.

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

/** True when a Bearer token exists — gate for any remote sync. */
export function hasAuthToken() {
  return Boolean(authToken());
}

// --- Shape mapping -------------------------------------------------------
// Local project (nested) <-> backend project (flat company fields).

function toApi(local) {
  const company = local.company || {};
  return {
    name: local.name || company.name || "Untitled project",
    company_name: company.name || "",
    pitch: company.pitch || "",
    industry: company.industry || "",
    business_model: company.business_model || "",
    website_url: company.website_url || "",
    targets: local.targets || {},
    audience: local.audience || {},
    competition: local.competition || {},
    brand_channels: local.brand_channels || {},
  };
}

function fromApi(remote) {
  return {
    id: remote.id,
    name: remote.name || "",
    createdAt: remote.created_at || "",
    updatedAt: remote.updated_at || "",
    company: {
      name: remote.company_name || "",
      pitch: remote.pitch || "",
      industry: remote.industry || "",
      business_model: remote.business_model || "",
      website_url: remote.website_url || "",
    },
    targets: remote.targets || {},
    audience: remote.audience || {},
    competition: remote.competition || {},
    brand_channels: remote.brand_channels || {},
  };
}

// --- CRUD ----------------------------------------------------------------

/** GET all projects for the current user. Returns local-shaped projects (or [] when unauthed/failed). */
export async function fetchProjectsRemote() {
  if (!hasAuthToken()) return [];
  try {
    const res = await fetch(`${BASE}/api/user/projects`, { headers: authHeaders() });
    if (!res.ok) return [];
    const rows = await res.json();
    return Array.isArray(rows) ? rows.map(fromApi) : [];
  } catch {
    return [];
  }
}

/** Upsert a local-shaped project by its id. Returns the server copy (local-shaped) or null. */
export async function upsertProjectRemote(local) {
  if (!hasAuthToken() || !local?.id) return null;
  try {
    const res = await fetch(`${BASE}/api/user/projects/${encodeURIComponent(local.id)}`, {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(toApi(local)),
    });
    if (!res.ok) return null;
    return fromApi(await res.json());
  } catch {
    return null;
  }
}

/** DELETE a project by id. Best-effort; never throws. */
export async function deleteProjectRemote(id) {
  if (!hasAuthToken() || !id) return;
  try {
    await fetch(`${BASE}/api/user/projects/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
  } catch {
    // best-effort
  }
}
