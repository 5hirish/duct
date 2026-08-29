"use client";

// Project memory client (/api/user/projects/{id}/memory) — the timeline behind
// what agents remember about a project: goals, incidents, metrics, decisions,
// actions, artifacts, each with its evidence and validity period.
//
// Superseded entries come back by default: the point of the timeline is that
// "we thought X, then learned Y" reads as history rather than as an error.
//
// Authenticated with the Bearer JWT + shared X-API-Key like the other
// user-scoped APIs (see authFetch.js).

import { BASE } from "./api";
import { authedHeaders } from "./authFetch";

// Mirror of backend models/memory.py — the vocabulary the UI filters on.
export const MEMORY_KINDS = Object.freeze([
  "goal",
  "decision",
  "incident",
  "status",
  "metric",
  "milestone",
  "event",
  "conclusion",
  "action",
  "watch",
  "entity",
  "artifact",
]);

export const MEMORY_KIND_ICONS = Object.freeze({
  goal: "🎯",
  decision: "⚖️",
  incident: "🔥",
  status: "📌",
  metric: "📈",
  milestone: "🏁",
  event: "⚡",
  conclusion: "💡",
  action: "🔧",
  watch: "👁",
  entity: "🏷",
  artifact: "📄",
});

async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { ...authedHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
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
 * List a project's memory, newest first.
 * Returns { items: [...], kinds: [...] } — `kinds` is what this project
 * actually has, so the filter chips reflect reality rather than the vocabulary.
 */
export async function listMemory({
  projectId,
  q,
  kind,
  entity,
  status,
  scope,
  fromDate,
  toDate,
  includeSuperseded = true,
  limit,
} = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  if (entity) params.set("entity", entity);
  if (status) params.set("status", status);
  if (scope) params.set("scope", scope);
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  if (limit) params.set("limit", String(limit));
  params.set("include_superseded", includeSuperseded ? "true" : "false");
  return request(`/api/user/projects/${projectId}/memory?${params}`);
}

/** One entry in full — the drawer behind a chip. */
export async function getMemory({ projectId, memoryId }) {
  return request(`/api/user/projects/${projectId}/memory/${memoryId}`);
}

/** "Remember this" — a user statement, which lands confirmed, not proposed. */
export async function createMemory({ projectId, ...entry }) {
  return request(`/api/user/projects/${projectId}/memory`, { method: "POST", body: entry });
}

/** Confirm, correct, pin or archive. Editing the text also confirms it. */
export async function updateMemory({ projectId, memoryId, ...patch }) {
  return request(`/api/user/projects/${projectId}/memory/${memoryId}`, {
    method: "PATCH",
    body: patch,
  });
}

export async function deleteMemory({ projectId, memoryId }) {
  return request(`/api/user/projects/${projectId}/memory/${memoryId}`, { method: "DELETE" });
}
