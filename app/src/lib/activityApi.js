"use client";

// Activity feed client (/api/user/activity) — the project's audit trail:
// change-set transitions, GTM publishes, artifact versions, each with actor
// attribution (user | agent | auto). Keyset-paginated via `before`.
//
// Authenticated with the Bearer JWT + shared X-API-Key like the other
// user-scoped APIs (see authFetch.js).

import { BASE } from "./api";
import { authedHeaders } from "./authFetch";

/**
 * List activity for a project, newest first.
 * Returns { items: [...], next_before: string|null } — pass next_before back
 * as `before` to fetch the next (older) page.
 */
export async function listActivity({ projectId, conversationId, category, before, limit } = {}) {
  const params = new URLSearchParams({ project_id: projectId });
  if (conversationId) params.set("conversation_id", conversationId);
  if (category) params.set("category", category);
  if (before) params.set("before", before);
  if (limit) params.set("limit", String(limit));

  const res = await fetch(`${BASE}/api/user/activity?${params}`, {
    headers: authedHeaders(),
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
  return res.json();
}
