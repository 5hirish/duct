/**
 * REST + SSE helpers for the Content Marketing Agent.
 * Talks directly to /api/content/* (not via /api/agents/...).
 */

import { BASE } from "./api";

function backendApiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = process.env.NEXT_PUBLIC_DUCT_API_KEY;
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
 * POST /api/content/plan/stream  body={project_id, start_date?}
 * Returns { body: ReadableStream, sessionId }.
 */
export async function openPlanStream({ projectId, startDate, signal } = {}) {
  const res = await fetch(`${BASE}/api/content/plan/stream`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      project_id: projectId,
      ...(startDate ? { start_date: startDate } : {}),
    }),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Plan stream failed: ${res.status}`);
  }
  const sessionId = res.headers.get("X-Content-Session-Id") || "";
  return { body: res.body, sessionId };
}

/**
 * POST /api/content/post/stream body={project_id, plan_id?, day_index?, topic?, pillar?}
 */
export async function openPostStream(
  { projectId, planId, dayIndex, topic, pillar } = {},
  { signal } = {},
) {
  const res = await fetch(`${BASE}/api/content/post/stream`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      project_id: projectId,
      ...(planId    ? { plan_id:    planId    } : {}),
      ...(dayIndex !== undefined && dayIndex !== null ? { day_index: dayIndex } : {}),
      ...(topic     ? { topic     } : {}),
      ...(pillar    ? { pillar    } : {}),
    }),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Post stream failed: ${res.status}`);
  }
  const sessionId = res.headers.get("X-Content-Session-Id") || "";
  return { body: res.body, sessionId };
}

export async function answerContentQuestions(sessionId, answers) {
  const res = await fetch(
    `${BASE}/api/content/answer/${encodeURIComponent(sessionId)}`,
    {
      method: "POST",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ answers }),
    },
  );
  return jsonOrThrow(res);
}

export async function sendContentChat(sessionId, content) {
  const res = await fetch(
    `${BASE}/api/content/chat/${encodeURIComponent(sessionId)}`,
    {
      method: "POST",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ content }),
    },
  );
  return jsonOrThrow(res);
}

export async function closeContentSession(sessionId) {
  if (!sessionId) return;
  await fetch(
    `${BASE}/api/content/session/${encodeURIComponent(sessionId)}`,
    { method: "DELETE", headers: backendApiHeaders() },
  ).catch(() => {});
}

// ---------------------------------------------------------------------------
// SSE frame parser
// ---------------------------------------------------------------------------

function parseSseDataFrame(frame) {
  const dataLines = frame
    .split("\n")
    .filter((l) => l.startsWith("data: "))
    .map((l) => l.slice(6));
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
}

export async function consumeSseStream(body, onEvent, signal) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) break;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (!frame.trim()) continue;
        const ev = parseSseDataFrame(frame);
        if (ev) onEvent(ev);
      }
    }
  } catch (err) {
    if (!signal?.aborted) throw err;
  } finally {
    reader.releaseLock();
  }
}

// ---------------------------------------------------------------------------
// CRUD — brand, plans, posts, formats, avatars, assets
// ---------------------------------------------------------------------------

export async function getBrandContext(projectId) {
  const res = await fetch(
    `${BASE}/api/content/brand?project_id=${encodeURIComponent(projectId)}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
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
  return jsonOrThrow(res);
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

export async function listPosts(projectId, { planId, status } = {}) {
  const params = new URLSearchParams({ project_id: projectId });
  if (planId) params.set("plan_id", planId);
  if (status) params.set("status", status);
  const res = await fetch(
    `${BASE}/api/content/posts?${params.toString()}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
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
  return jsonOrThrow(res);
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
  return jsonOrThrow(res);
}

export async function publishPost(postId, { accountIds, scheduledAt } = {}) {
  const res = await fetch(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}/publish`,
    {
      method: "POST",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        account_ids: accountIds,
        ...(scheduledAt ? { scheduled_at: scheduledAt } : {}),
      }),
    },
  );
  return jsonOrThrow(res);
}

export async function syncPostMetrics(postId) {
  const res = await fetch(
    `${BASE}/api/content/posts/${encodeURIComponent(postId)}/sync-metrics`,
    { method: "POST", headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
}

export async function listSocialAccounts(projectId, platform) {
  const url = new URL(`${BASE}/api/content/social-accounts`);
  url.searchParams.set("project_id", projectId);
  if (platform) url.searchParams.set("platform", platform);
  const res = await fetch(url.toString(), { headers: backendApiHeaders() });
  return jsonOrThrow(res);
}

export async function listFormats(projectId) {
  const res = await fetch(
    `${BASE}/api/content/formats?project_id=${encodeURIComponent(projectId)}`,
    { headers: backendApiHeaders() },
  );
  return jsonOrThrow(res);
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
