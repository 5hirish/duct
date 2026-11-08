"use client";

// Activity feed client (/api/user/activity) — the project's audit trail:
// change-set transitions, GTM publishes, artifact versions, each with actor
// attribution (user | agent | auto). Keyset-paginated via `before`.
//
// Authenticated with the Bearer JWT + shared X-API-Key like the other
// user-scoped APIs (see authFetch.js).

import { authedRequest } from "./authFetch";

/**
 * List activity for a project, newest first.
 * Returns { items: [...], next_before: string|null } — pass next_before back
 * as `before` to fetch the next (older) page.
 */
export function listActivity({ projectId, conversationId, category, before, limit } = {}) {
  const params = new URLSearchParams({ project_id: projectId });
  if (conversationId) params.set("conversation_id", conversationId);
  if (category) params.set("category", category);
  if (before) params.set("before", before);
  if (limit) params.set("limit", String(limit));

  return authedRequest(`/api/user/activity?${params}`);
}

/** An agent's edit to a project (MCP `update_project`). The backend's
 *  ACTION_EDITED in service/project_writes.py; the feed offers Undo on it. */
export const ACTION_PROJECT_EDITED = "project.edited";

/**
 * Put back what one agent edit replaced. Resolves to `{ restored, skipped,
 * project }`: a field changed again since the edit is skipped, never reverted.
 */
export function undoProjectEdit(projectId, activityId) {
  return authedRequest(
    `/api/user/projects/${encodeURIComponent(projectId)}/edits/${encodeURIComponent(activityId)}/undo`,
    { method: "POST" },
  );
}
