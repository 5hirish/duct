/**
 * REST + SSE helpers for the Content Studio agent.
 *
 * Session lifecycle (plan/post drafting, chat, answers, close) runs through the
 * unified /api/agents/tiktok_studio/* endpoints — same pattern as the SEO audit
 * workspace. The content-specific CRUD + slide-render routes still live under
 * /api/content/*.
 */

import {
  BASE,
  backendApiKey,
  createAgentSession,
  openAgentStream,
  sendAgentMessage,
  closeAgentSession,
  getAgentConversation,
  listAgentConversations,
  archiveAgentConversation,
} from "./api.js";
import { cached, invalidate } from "./contentCache.js";

/** Unified agent-type id for this workspace (see backend agents/registry.py). */
const AGENT_TYPE = "tiktok_studio";

// Cache TTLs (ms). Short — these only smooth out tab-switch refetches.
const TTL_POSTS     = 60_000;
const TTL_BRAND     = 120_000;
const TTL_ANALYTICS = 120_000;
const TTL_FORMATS   = 120_000;

/** Resolve a backend-relative asset URL (e.g. /uploads/...) to an absolute URL. */
export function mediaUrl(u) {
  if (!u) return "";
  if (/^(https?:|data:|blob:)/i.test(u)) return u;
  return `${BASE}${u.startsWith("/") ? "" : "/"}${u}`;
}

/**
 * Thumbnail variant of an absolute image URL. When the media domain has
 * Cloudflare Image Resizing enabled (NEXT_PUBLIC_CDN_IMAGE_RESIZING="true"),
 * rewrites to a width-capped, auto-format (WebP/AVIF) render via /cdn-cgi/image/
 * — so the board/list pull small images while the editor keeps full-res. Safe
 * passthrough (returns the URL unchanged) when disabled or for relative/data URLs.
 */
export function cdnImage(u, { width = 480, quality = 80 } = {}) {
  if (!u || process.env.NEXT_PUBLIC_CDN_IMAGE_RESIZING !== "true") return u;
  if (!/^https?:\/\//i.test(u)) return u;
  try {
    const url = new URL(u);
    const opts = `width=${width},quality=${quality},format=auto,fit=scale-down`;
    return `${url.origin}/cdn-cgi/image/${opts}${url.pathname}${url.search}`;
  } catch {
    return u;
  }
}

function backendApiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = backendApiKey();
  if (key) headers["X-API-Key"] = key;
  return headers;
}

async function jsonOrThrow(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ---------------------------------------------------------------------------
// SSE — plan/post stream lifecycle
// ---------------------------------------------------------------------------

/**
 * Start a 30-day plan session via the unified agent API:
 *   POST /api/agents/tiktok_studio/sessions  body={mode:"plan_month", project_id, start_date?}
 *   GET  /api/agents/tiktok_studio/sessions/{id}/stream
 * Returns { body: ReadableStream, sessionId }. Events emitted between create and
 * stream-open are buffered server-side in the session queue, so none are lost.
 */
export async function openPlanStream(
  { projectId, startDate, conversationId, resume, startFresh, artifactType, artifactId } = {},
  { signal, onSession } = {},
) {
  const { session_id, conversation_id } = await createAgentSession(AGENT_TYPE, {
    mode: "plan_month",
    project_id: projectId,
    ...(startDate ? { start_date: startDate } : {}),
    ...resumeFields({ conversationId, resume, startFresh, artifactType, artifactId }),
  });
  // Surface the ids the instant the backend session exists (and its worker is
  // spawned) — before the abortable stream open — so the caller can close an
  // orphaned session if it was torn down mid-create (e.g. StrictMode remount).
  onSession?.({ sessionId: session_id, conversationId: conversation_id });
  const body = await openAgentStream(AGENT_TYPE, session_id, { signal });
  return { body, sessionId: session_id, conversationId: conversation_id };
}

/**
 * Start a single-post draft session via the unified agent API:
 *   POST /api/agents/tiktok_studio/sessions  body={mode:"draft_post", project_id, plan_id?, day_index?, topic?, pillar?, channel?}
 *   GET  /api/agents/tiktok_studio/sessions/{id}/stream
 */
export async function openPostStream(
  { projectId, planId, dayIndex, topic, pillar, channel,
    conversationId, resume, startFresh, artifactType, artifactId } = {},
  { signal, onSession } = {},
) {
  const { session_id, conversation_id } = await createAgentSession(AGENT_TYPE, {
    mode: "draft_post",
    project_id: projectId,
    ...(planId    ? { plan_id:    planId    } : {}),
    ...(dayIndex !== undefined && dayIndex !== null ? { day_index: dayIndex } : {}),
    ...(topic     ? { topic     } : {}),
    ...(pillar    ? { pillar    } : {}),
    ...(channel   ? { channel   } : {}),
    ...resumeFields({ conversationId, resume, startFresh, artifactType, artifactId }),
  });
  onSession?.({ sessionId: session_id, conversationId: conversation_id });
  const body = await openAgentStream(AGENT_TYPE, session_id, { signal });
  return { body, sessionId: session_id, conversationId: conversation_id };
}

/** Conversation/resume body fields shared by the openers — omitted keys keep
 * the normal first-open behaviour (server auto-creates a fresh conversation). */
function resumeFields({ conversationId, resume, startFresh, artifactType, artifactId } = {}) {
  return {
    ...(conversationId ? { conversation_id: conversationId } : {}),
    ...(resume         ? { resume: true } : {}),
    ...(startFresh     ? { start_fresh: true } : {}),
    ...(artifactType   ? { artifact_type: artifactType } : {}),
    ...(artifactId     ? { artifact_id: artifactId } : {}),
  };
}

/** Fetch a content conversation + its event log for chat rehydration. */
export async function getContentConversation(conversationId) {
  return getAgentConversation(AGENT_TYPE, conversationId);
}

/** List content conversations (resume lookup / history). */
export async function listContentConversations(filters) {
  return listAgentConversations(AGENT_TYPE, filters);
}

/** Archive a content conversation (start-fresh support). */
export async function archiveContentConversation(conversationId) {
  if (!conversationId) return;
  await archiveAgentConversation(AGENT_TYPE, conversationId).catch(() => {});
}

/**
 * Re-attach to an EXISTING session's SSE stream (no new session created). Works
 * while the backend's reconnect grace window is still open; throws if the
 * session is already gone (caller then falls back to a resume-create).
 */
export async function reattachContentStream(sessionId, { signal } = {}) {
  return openAgentStream(AGENT_TYPE, sessionId, { signal });
}

export async function answerContentQuestions(sessionId, answers) {
  return sendAgentMessage(AGENT_TYPE, sessionId, { type: "answer", answers });
}

export async function sendContentChat(sessionId, content) {
  return sendAgentMessage(AGENT_TYPE, sessionId, { type: "chat", content });
}

export async function closeContentSession(sessionId) {
  if (!sessionId) return;
  await closeAgentSession(AGENT_TYPE, sessionId).catch(() => {});
}

/** GET a self-contained 1080×1920 single-slide doc (images inlined) to rasterize. */
export async function getSlideRenderDoc(sessionId, postId, slideId) {
  const url =
    `${BASE}/api/content/slide-doc/${encodeURIComponent(sessionId)}` +
    `?post_id=${encodeURIComponent(postId)}&slide_id=${encodeURIComponent(slideId)}`;
  const res = await fetch(url, { headers: backendApiHeaders() });
  return jsonOrThrow(res);
}

/** POST a rasterized slide PNG back to resolve the agent's render_slide request. */
export async function postSlideRender(sessionId, { render_id, image_base64 }) {
  const res = await fetch(
    `${BASE}/api/content/slide-render/${encodeURIComponent(sessionId)}`,
    {
      method: "POST",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ render_id, image_base64 }),
    },
  );
  return jsonOrThrow(res);
}

// Re-exported so the many `import { consumeSseStream } from "@/lib/contentApi"`
// call sites keep working; the implementation lives in lib/sse.js.
export { consumeSseStream, parseSseDataFrame } from "./sse";

// ---------------------------------------------------------------------------
// CRUD — brand, plans, posts, formats, avatars, assets
// ---------------------------------------------------------------------------

export async function getBrandContext(projectId) {
  return cached(`brand:${projectId}`, TTL_BRAND, async () => {
    const res = await fetch(
      `${BASE}/api/content/brand?project_id=${encodeURIComponent(projectId)}`,
      { headers: backendApiHeaders() },
    );
    return jsonOrThrow(res);
  });
}

export async function putBrandContext(projectId, body) {
  const res = await fetch(
    `${BASE}/api/content/brand?project_id=${encodeURIComponent(projectId)}`,
    {
      method: "PUT",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    },
  );
  const out = await jsonOrThrow(res);
  invalidate(`brand:${projectId}`);
  return out;
}

export async function listPlans(projectId) {
  const res = await fetch(
    `${BASE}/api/content/plans?project_id=${encodeURIComponent(projectId)}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function getPlan(planId) {
  const res = await fetch(
    `${BASE}/api/content/plans/${encodeURIComponent(planId)}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function patchPlanDay(planId, day, patch) {
  const res = await fetch(
    `${BASE}/api/content/plans/${encodeURIComponent(planId)}/days/${day}`,
    {
      method: "PATCH",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(patch),
    },
  );
  return jsonOrThrow(res);
}

// Posts + their PostBridge-sourced analytics both depend on post state, so any
// post write clears both. Broad (prefix) invalidation keeps it simple and safe.
function invalidatePosts() {
  invalidate("posts:");
  invalidate("analytics:");
}

export async function listPosts(projectId, { planId, status } = {}) {
  return cached(`posts:${projectId}:${planId || ""}:${status || ""}`, TTL_POSTS, async () => {
    const params = new URLSearchParams({ project_id: projectId });
    if (planId) params.set("plan_id", planId);
    if (status) params.set("status", status);
    const res = await fetch(
      `${BASE}/api/content/posts?${params.toString()}`,
      { headers: backendApiHeaders() },
    );
    return jsonOrThrow(res);
  });
}

export async function getPost(postId) {
  const res = await fetch(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function patchPost(postId, patch) {
  const res = await fetch(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}`,
    {
      method: "PATCH",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(patch),
    },
  );
  const out = await jsonOrThrow(res);
  invalidatePosts();
  return out;
}

export async function markPostPosted(postId, { tiktokUrl } = {}) {
  const url = new URL(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}/mark-posted`,
  );
  if (tiktokUrl) url.searchParams.set("tiktok_url", tiktokUrl);
  const res = await fetch(url.toString(), {
    method: "POST",
    headers: backendApiHeaders(),
  });
  const out = await jsonOrThrow(res);
  invalidatePosts();
  return out;
}

/**
 * POST /api/content/posts/{id}/publish — uploads each linked image to
 * PostBridge then creates the post.
 *
 * @param postId          Content post UUID
 * @param socialAccountIds Numeric PostBridge social account IDs
 * @param scheduledAt     ISO 8601 string (optional; omit to post now)
 * @param tiktokDraft     true → land as a TikTok draft, false → schedule/post
 */
export async function publishPost(postId, { socialAccountIds, scheduledAt, tiktokDraft = false } = {}) {
  const res = await fetch(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}/publish`,
    {
      method: "POST",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        social_account_ids: socialAccountIds,
        ...(scheduledAt ? { scheduled_at: scheduledAt } : {}),
        tiktok_draft: tiktokDraft,
      }),
    },
  );
  const out = await jsonOrThrow(res);
  invalidatePosts();
  return out;
}

export async function syncPostDaily(postId) {
  const res = await fetch(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}/sync-daily`,
    { method: "POST", headers: backendApiHeaders() },
  );
  const out = await jsonOrThrow(res);
  invalidatePosts();
  return out;
}

export async function syncPostMetrics(postId) {
  const res = await fetch(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}/sync-metrics`,
    { method: "POST", headers: backendApiHeaders() },
  );
  const out = await jsonOrThrow(res);
  invalidatePosts();
  return out;
}

export async function listSocialAccounts(projectId, platform) {
  const url = new URL(`${BASE}/api/content/social-accounts`);
  url.searchParams.set("project_id", projectId);
  if (platform) url.searchParams.set("platform", platform);
  const res = await fetch(url.toString(), { headers: backendApiHeaders() });
  return jsonOrThrow(res);
}

/**
 * Per-post analytics for the project's linked accounts, pulled live from
 * PostBridge. Pass { refresh: true } to trigger a PostBridge sync first.
 */
export async function getContentAnalytics(projectId, { refresh = false } = {}) {
  const fetchIt = async () => {
    const url = new URL(`${BASE}/api/content/analytics`);
    url.searchParams.set("project_id", projectId);
    if (refresh) url.searchParams.set("refresh", "true");
    const res = await fetch(url.toString(), { headers: backendApiHeaders() });
    return jsonOrThrow(res);
  };
  // Explicit refresh drops the cache first, then fetches live + repopulates.
  if (refresh) invalidate(`analytics:${projectId}`);
  return cached(`analytics:${projectId}`, TTL_ANALYTICS, fetchIt);
}

/** The social accounts this project has linked (persisted selection). */
export async function listLinkedAccounts(projectId) {
  const url = new URL(`${BASE}/api/content/linked-accounts`);
  url.searchParams.set("project_id", projectId);
  const res = await fetch(url.toString(), { headers: backendApiHeaders() });
  return jsonOrThrow(res);
}

/**
 * Replace the project's linked-account set.
 * accounts: [{ account_id: number, platform: string, username: string }]
 */
export async function saveLinkedAccounts(projectId, accounts) {
  const res = await fetch(`${BASE}/api/content/linked-accounts`, {
    method: "PUT",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ project_id: projectId, accounts }),
  });
  const out = await jsonOrThrow(res);
  // Analytics is scoped to linked platforms — changing the set changes it.
  invalidate(`analytics:${projectId}`);
  return out;
}

/** GET /api/content/styles — shared, read-only style registry (base_css + styles[]). */
export async function listStyles() {
  return cached("styles:global", TTL_FORMATS, async () => {
    const res = await fetch(`${BASE}/api/content/styles`, { headers: backendApiHeaders() });
    return jsonOrThrow(res);
  });
}

export async function listFormats(projectId) {
  return cached(`formats:${projectId}`, TTL_FORMATS, async () => {
    const res = await fetch(
      `${BASE}/api/content/formats?project_id=${encodeURIComponent(projectId)}`,
      { headers: backendApiHeaders() },
    );
    return jsonOrThrow(res);
  });
}

/**
 * POST /api/content/formats — create or update (idempotent on project_id+slug).
 * body = { projectId, slug, name, data }
 */
export async function upsertFormat({ projectId, slug, name = "", data = {} }) {
  const res = await fetch(`${BASE}/api/content/formats`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ project_id: projectId, slug, name, data }),
  });
  const out = await jsonOrThrow(res);
  invalidateFormats();
  return out;
}

/** PATCH /api/content/formats/{id} — full FormatIn body required by the backend. */
export async function patchFormat(formatId, { projectId, slug, name = "", data = {} }) {
  const res = await fetch(`${BASE}/api/content/formats/${formatId}`, {
    method: "PATCH",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ project_id: projectId, slug, name, data }),
  });
  const out = await jsonOrThrow(res);
  invalidateFormats();
  return out;
}

/** DELETE /api/content/formats/{id} */
export async function deleteFormat(formatId) {
  const res = await fetch(`${BASE}/api/content/formats/${formatId}`, {
    method: "DELETE",
    headers: backendApiHeaders(),
  });
  const out = await jsonOrThrow(res);
  invalidateFormats();
  return out;
}

// A format edit changes the format name posts render, so clear posts too.
function invalidateFormats() {
  invalidate("formats:");
  invalidate("posts:");
}

export async function listAvatars(projectId) {
  const res = await fetch(
    `${BASE}/api/content/avatars?project_id=${encodeURIComponent(projectId)}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function listAssets(projectId, { assetType, postId } = {}) {
  const params = new URLSearchParams({ project_id: projectId });
  if (assetType) params.set("asset_type", assetType);
  if (postId)    params.set("post_id", postId);
  const res = await fetch(
    `${BASE}/api/content/assets?${params.toString()}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function uploadAsset(projectId, assetType, file) {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("asset_type", assetType);
  form.append("file", file);
  const res = await fetch(`${BASE}/api/content/uploads`, {
    method: "POST",
    headers: backendApiHeaders(),  // do NOT set Content-Type — browser adds boundary
    body: form,
  });
  return jsonOrThrow(res);
}


// ---------------------------------------------------------------------------
// Discovery (Apify TikTok scraper)
// ---------------------------------------------------------------------------

export async function startDiscoverRun({ projectId, actorId, inputPayload }) {
  const res = await fetch(`${BASE}/api/content/discover/start`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      project_id:    projectId,
      actor_id:      actorId,
      input_payload: inputPayload || {},
    }),
  });
  return jsonOrThrow(res);
}

export async function getDiscoverRunStatus(runId) {
  const res = await fetch(
    `${BASE}/api/content/discover/status/${encodeURIComponent(runId)}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function getDiscoverResults(datasetId, limit = 200) {
  const res = await fetch(
    `${BASE}/api/content/discover/results/${encodeURIComponent(datasetId)}?limit=${limit}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function saveDiscoveredReference({ projectId, actorId, runId, datasetId, request, post }) {
  const res = await fetch(`${BASE}/api/content/discover/save`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      project_id: projectId,
      actor_id:   actorId,
      run_id:     runId,
      dataset_id: datasetId,
      request:    request || {},
      post,
    }),
  });
  return jsonOrThrow(res);
}
