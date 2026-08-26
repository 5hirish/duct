"use client";

// Artifact library client (/api/user/artifacts) — durable agent outputs.
// Listing returns the newest version per artifact group; content bytes are
// served only through these authed endpoints (Bearer JWT), never a public URL.

import { BASE } from "./api";
import { authedHeaders, authedRequest } from "./authFetch";

export function listArtifacts({ projectId, kind = "", agentType = "", conversationId = "", limit = 50 } = {}) {
  const params = new URLSearchParams({ project_id: projectId });
  if (kind) params.set("kind", kind);
  if (agentType) params.set("agent_type", agentType);
  if (conversationId) params.set("conversation_id", conversationId);
  if (limit) params.set("limit", String(limit));
  return authedRequest(`/api/user/artifacts?${params}`);
}

export function getArtifact(artifactId) {
  return authedRequest(`/api/user/artifacts/${artifactId}`);
}

export function listArtifactVersions(artifactId) {
  return authedRequest(`/api/user/artifacts/${artifactId}/versions`);
}

export function deleteArtifact(artifactId) {
  return authedRequest(`/api/user/artifacts/${artifactId}`, { method: "DELETE" });
}

/** Resolve a slug / group id / version id / pasted URL to the latest version. */
export function resolveArtifact(projectId, ref) {
  const params = new URLSearchParams({ project_id: projectId, ref });
  return authedRequest(`/api/user/artifacts/resolve?${params}`);
}

/** Promote an old snapshot to a new head version (history preserved). */
export function restoreArtifactVersion(artifactId) {
  return authedRequest(`/api/user/artifacts/${artifactId}/restore`, { method: "POST" });
}

/** Unified diff of a version against another ("prev" = previous version). */
export function diffArtifact(artifactId, against = "prev") {
  const params = new URLSearchParams({ against });
  return authedRequest(`/api/user/artifacts/${artifactId}/diff?${params}`);
}

/** Derived export (pdf | csv | md) of one version — triggers a browser download. */
export async function exportArtifact(artifact, format) {
  const res = await fetch(`${BASE}/api/user/artifacts/${artifact.id}/export?format=${format}`, {
    headers: authedHeaders(),
  });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch { /* non-JSON */ }
    throw new Error(detail || `Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const stem = (artifact.filename || artifact.slug || "artifact").replace(/\.[a-z0-9]+$/i, "");
  a.download = `${stem}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Raw stored bytes as text (freehand HTML, markdown, …). Throws on 404. */
export async function getArtifactContent(artifactId) {
  const res = await fetch(`${BASE}/api/user/artifacts/${artifactId}/content`, {
    headers: authedHeaders(),
  });
  if (!res.ok) throw new Error(`Content unavailable (${res.status})`);
  return res.text();
}

/** Trigger a browser download of the artifact's stored file. */
export async function downloadArtifact(artifact) {
  const res = await fetch(`${BASE}/api/user/artifacts/${artifact.id}/download`, {
    headers: authedHeaders(),
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = artifact.filename || "artifact";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
