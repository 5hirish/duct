"use client";

// What the desk loads, and the two things it writes.
//
// Six independent reads, issued together rather than in sequence: a page that
// awaits each in turn spends six round-trips before it paints anything. When
// one source fails the rest still render — a project with no change sets, or a
// user whose execution scope is missing, must not blank the whole page. A
// single `GET /projects/{id}/desk` is the right end state; this keeps the
// aggregation in the client until the shape has settled.

import { listAgentConversations, patchAgentConversation } from "./api";
import { authedRequest } from "./authFetch";
import { listActivity } from "./activityApi";
import { listArtifacts } from "./artifactsApi";
import { listChangeSets } from "./executionApi";
import { listMemory } from "./memoryApi";
import {
  connectedConnectorTypes,
  listAccountDataSources,
  listProjectDataSources,
} from "./connectorsApi";
import { connectedCount } from "./dataSources";

/** The agent whose threads and documents this desk is for. */
export const INSIGHTS_AGENT = "insights";

export function listInsightsConversations(projectId, { includeArchived = false } = {}) {
  return listAgentConversations(INSIGHTS_AGENT, { projectId, includeArchived });
}

/** Pin or unpin a thread. Applies to the conversation; nothing else changes. */
export function pinConversation(conversationId, pinned) {
  return patchAgentConversation(INSIGHTS_AGENT, conversationId, { pinned });
}

/** Pin or unpin a document. The backend applies it to the whole version group. */
export function pinArtifact(artifactId, pinned) {
  return authedRequest(`/api/user/artifacts/${artifactId}`, {
    method: "PATCH",
    body: { pinned },
  });
}

/** Resolve a promise to a fallback rather than letting one source blank the page. */
async function orEmpty(promise, fallback) {
  try {
    return await promise;
  } catch {
    return fallback;
  }
}

/**
 * How many data sources this desk can actually reach.
 *
 * The server resolves this: it walks the whole connector registry, so an
 * API-key connector counts exactly like an OAuth one, and it applies the
 * project's account bindings. Falling back to the browser's own view matters —
 * signed out, offline, or against a backend without the route, the tab may
 * still hold session-only OAuth tokens, and answering "zero" then is the same
 * lie this function was written to stop telling.
 */
async function countSources(projectId) {
  const rows = await orEmpty(
    projectId ? listProjectDataSources(projectId) : listAccountDataSources(),
    null
  );
  if (Array.isArray(rows)) return connectedCount(rows);
  const types = await orEmpty(connectedConnectorTypes(), new Set());
  return types?.size ?? 0;
}

/**
 * Everything the desk shows, in one await.
 *
 * Change sets come back user-scoped rather than project-scoped, so they are
 * filtered here; every other source is already asked for one project.
 */
export async function loadDesk({ projectId, activityLimit = 12, memoryLimit = 60 }) {
  // Asked before the project guard below, not inside it: someone who has
  // connected three sources but not yet created a project still has three
  // sources, and the checklist asks them to do those two things in that order —
  // so a hardcoded zero here told the truest possible beginner they had
  // connected nothing.
  const sources = countSources(projectId);

  if (!projectId) {
    return {
      memories: [],
      conversations: [],
      artifacts: [],
      activity: [],
      changeSets: [],
      sourceCount: await sources,
    };
  }

  const [memory, conversations, artifacts, activity, changeSets, connected] = await Promise.all([
    orEmpty(listMemory({ projectId, limit: memoryLimit, includeSuperseded: false }), { items: [] }),
    orEmpty(listInsightsConversations(projectId), []),
    orEmpty(listArtifacts({ projectId, agentType: INSIGHTS_AGENT, limit: 50 }), []),
    orEmpty(listActivity({ projectId, limit: activityLimit }), { items: [] }),
    orEmpty(listChangeSets(), []),
    sources,
  ]);

  return {
    memories: memory?.items || [],
    conversations: Array.isArray(conversations) ? conversations : [],
    artifacts: Array.isArray(artifacts) ? artifacts : [],
    activity: activity?.items || [],
    changeSets: (Array.isArray(changeSets) ? changeSets : []).filter(
      (c) => !c.project_id || c.project_id === projectId
    ),
    sourceCount: connected,
  };
}
