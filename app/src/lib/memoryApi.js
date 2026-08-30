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

// --- Controls -------------------------------------------------------------
// Pause stops Duct *learning*; it never hides what is already known. Reset is
// the one irreversible verb, so it demands confirm and export exists beside it.

export async function setMemoryPaused({ projectId, paused }) {
  return request(`/api/user/projects/${projectId}/memory/pause`, {
    method: "POST",
    body: { paused },
  });
}

export async function resetMemory({ projectId }) {
  return request(`/api/user/projects/${projectId}/memory/reset?confirm=true`, { method: "POST" });
}

export async function exportMemory({ projectId }) {
  return request(`/api/user/projects/${projectId}/memory/export`);
}

// --- User scope (/api/user/memory) ----------------------------------------
// What Duct knows about the person rather than the account: how they want
// analysis done, what they read, what they ignore. Crosses projects.

export const USER_MEMORY_KINDS = Object.freeze([
  "identity",
  "communication",
  "method",
  "tooling",
  "process",
  "feedback",
]);

export async function listUserMemory({ q, kind } = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  return request(`/api/user/memory?${params}`);
}

export async function createUserMemory(entry) {
  return request("/api/user/memory", { method: "POST", body: entry });
}

export async function updateUserMemory({ memoryId, ...patch }) {
  return request(`/api/user/memory/${memoryId}`, { method: "PATCH", body: patch });
}

export async function deleteUserMemory({ memoryId }) {
  return request(`/api/user/memory/${memoryId}`, { method: "DELETE" });
}

export async function setUserMemoryPaused({ paused }) {
  return request("/api/user/memory/pause", { method: "POST", body: { paused } });
}

export async function resetUserMemory() {
  return request("/api/user/memory/reset?confirm=true", { method: "POST" });
}

export async function exportUserMemory() {
  return request("/api/user/memory/export");
}

/** Save an export as a JSON file — the "it's yours" half of pause/reset/export. */
export function downloadJson(data, filename) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
