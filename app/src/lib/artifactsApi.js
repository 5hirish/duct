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
