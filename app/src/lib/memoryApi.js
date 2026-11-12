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

import { msg } from "@lingui/core/macro";
import { authedRequest } from "./authFetch";

// Mirror of backend models/memory.py — the vocabulary the UI filters on.
export const MEMORY_KINDS = Object.freeze([
  "rule",
  "goal",
  "decision",
  "incident",
  "status",
  "metric",
  "event",
  "outcome",
  "conclusion",
  "action",
  "watch",
  "entity",
  "artifact",
]);

export const MEMORY_KIND_ICONS = Object.freeze({
  rule: "🛡",
  goal: "🎯",
  decision: "⚖️",
  incident: "🔥",
  status: "📌",
  metric: "📈",
  event: "⚡",
  outcome: "📊",
  conclusion: "💡",
  action: "🔧",
  watch: "👁",
  entity: "🏷",
  artifact: "📄",
});

// What the page filters and files by. The backend keeps twelve project kinds
// and four personal ones because the agents need that precision (a metric
// expires, a decision does not); a person looking for "what does Duct think
// our goals are" does not. Each group names the kinds it covers, and the
// first kind is what "Remember" files a new entry under. A group with
// `create: false` is listed but never offered in the form.
export const PROJECT_KIND_GROUPS = Object.freeze([
  { id: "rules", label: msg`Rules`, kinds: ["rule"] },
  { id: "goals", label: msg`Goals`, kinds: ["goal"] },
  { id: "facts", label: msg`Facts`, kinds: ["entity", "status"] },
  { id: "numbers", label: msg`Numbers`, kinds: ["metric"] },
  { id: "findings", label: msg`Findings`, kinds: ["conclusion", "incident", "watch"] },
  { id: "outcomes", label: msg`Outcomes`, kinds: ["outcome"] },
  { id: "decisions", label: msg`Decisions`, kinds: ["decision", "action", "event"] },
  { id: "feedback", label: msg`Feedback`, kinds: ["feedback"] },
  { id: "reports", label: msg`Reports`, kinds: ["artifact"], create: false },
]);

export const USER_KIND_GROUPS = Object.freeze([
  { id: "about", label: msg`About you`, kinds: ["identity"] },
  { id: "style", label: msg`Style`, kinds: ["communication"] },
  { id: "methods", label: msg`Methods`, kinds: ["method"] },
  { id: "corrections", label: msg`Corrections`, kinds: ["feedback"] },
]);

const request = authedRequest;

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

// --- User scope (/api/user/memory) ----------------------------------------
// What Duct knows about the person rather than the account: how they want
// analysis done, what they read, what they ignore. Crosses projects.

export const USER_MEMORY_KINDS = Object.freeze([
  "identity",
  "communication",
  "method",
  "feedback",
]);

/** The caller's own memory, private to them whatever their role. */
export async function listUserMemory({
  q,
  kind,
  projectId,
  status,
  fromDate,
  toDate,
  includeSuperseded = true,
  limit,
} = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  // What is private to this project, on top of what holds everywhere.
  if (projectId) params.set("project_id", projectId);
  if (status) params.set("status", status);
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  if (limit) params.set("limit", String(limit));
  params.set("include_superseded", includeSuperseded ? "true" : "false");
  return request(`/api/user/memory?${params}`);
}

/** Make a private entry hold on one project (`projectId`) or on every project (""). */
export async function moveUserMemory({ memoryId, projectId = "" }) {
  return request(`/api/user/memory/${memoryId}/move`, {
    method: "POST",
    body: { project_id: projectId },
  });
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


