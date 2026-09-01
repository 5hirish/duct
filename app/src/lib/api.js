import { googleAdsByoCredentials } from "./adsCredentials.js";
import { providerKeyHeaders } from "./providerKeys.js";
import { consumeSseStream } from "./sse.js";
// Bearer JWT minted by Google Sign-In. Optional: signed-out sessions omit it and
// the backend personalises only when a valid token is present.
import { authToken } from "./authFetch.js";

const configuredBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const normalizedConfiguredBase = configuredBase?.replace(/\/+$/, "");
const isProduction = process.env.NODE_ENV === "production";

/**
 * In production, require an explicit API base URL.
 * This prevents silently sending real users to localhost when env vars are missing.
 */
const hostedBase = normalizedConfiguredBase || (isProduction ? "" : "http://localhost:8002");

/**
 * Origin every request is sent to.
 *
 * `let`, not `const`, on purpose: the desktop shell bundles its own backend and
 * only learns its loopback port at runtime, so `useLocalBackend()` repoints this
 * once at boot (see `localBackend.js`). ES module live bindings mean every
 * `${BASE}/…` call site picks the new value up with no change of its own —
 * which is why callers must read `BASE` at call time and never copy it into
 * their own module-level constant.
 */
export let BASE = hostedBase;

/** Must match backend DUCT_API_KEY. Prefer a Next server proxy in production so this is not public. */
let apiKey = process.env.NEXT_PUBLIC_DUCT_API_KEY || "";

/** The `X-API-Key` for the active backend. Shared so every api module agrees. */
export function backendApiKey() {
  return apiKey;
}

/**
 * Point the app at the desktop shell's local sidecar instead of the hosted API.
 *
 * Called once, before the first request, by the desktop boot gate. The local
 * key is generated per install and read from the OS-protected data dir, so it
 * is not a secret shared with anyone else.
 */
export function useLocalBackend({ url, apiKey: localKey }) {
  BASE = String(url || "").replace(/\/+$/, "");
  apiKey = localKey || "";
}

function backendApiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = backendApiKey();
  if (key) {
    headers["X-API-Key"] = key;
  }
  return headers;
}

/**
 * Headers that prove both halves: the X-API-Key says "this is the Duct app",
 * the Bearer token says which user is asking. Anything reading or writing
 * project-scoped data needs the second — the key is public, it ships in this
 * bundle. Exported so `contentApi` and friends share this one definition
 * rather than each keeping a key-only copy.
 */
export function backendAuthedHeaders(extra = {}) {
  const headers = backendApiHeaders(extra);
  const token = authToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export async function fetchConnectorAccounts(connectorId, refreshToken, extras = {}) {
  const res = await fetch(
    `${BASE}/api/connectors/${encodeURIComponent(connectorId)}/accounts`,
    {
      method: "POST",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ refresh_token: refreshToken, ...extras }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  const payload = await res.json();
  return payload.accounts ?? [];
}

export async function fetchGoogleAdsAccounts(refreshToken) {
  return fetchConnectorAccounts("google_ads", refreshToken, await googleAdsByoCredentials());
}

export async function fetchGa4Properties(refreshToken) {
  return fetchConnectorAccounts("ga4", refreshToken);
}

export async function fetchGscSites(refreshToken) {
  return fetchConnectorAccounts("gsc", refreshToken);
}

/**
 * Fetch per-engine availability for the engine picker.
 * Returns a map keyed by engine key, e.g. { v3: { status, auth_method, supports_oauth, detail } }.
 * On any failure returns {} — callers treat an unknown engine as available so
 * the picker never becomes unusable when the backend is unreachable.
 */
export async function fetchEngineStatus() {
  try {
    const res = await fetch(`${BASE}/api/engines/status`, {
      headers: backendApiHeaders(),
    });
    if (!res.ok) return {};
    const payload = await res.json();
    const map = {};
    for (const engine of payload.engines ?? []) {
      map[engine.key] = engine;
    }
    return map;
  } catch {
    return {};
  }
}

export async function generateReport(params) {
  const res = await fetch(`${BASE}/api/insights/generate`, {
    method: "POST",
    headers: { ...backendAuthedHeaders({ "Content-Type": "application/json" }), ...(await providerKeyHeaders()) },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  return res.json();
}

export async function refreshInsightBriefs(routine) {
  const refreshToken = sessionStorage.getItem("gads_refresh_token") || "";
  const ga4RefreshToken = sessionStorage.getItem("ga4_refresh_token") || "";
  const gscRefreshToken = sessionStorage.getItem("gsc_refresh_token") || "";
  const body = {
    connections: routine?.connections || [],
    date_preset: routine?.date_preset || "30",
    date_from: routine?.custom_date_from || "",
    date_to: routine?.custom_date_to || "",
    refresh_token: refreshToken,
    developer_token: (await googleAdsByoCredentials()).developer_token,
    ga4_refresh_token: ga4RefreshToken,
    gsc_refresh_token: gscRefreshToken,
    targets: routine?.targets || {},
  };
  const res = await fetch(`${BASE}/api/insights/refresh`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  return res.json();
}

export async function streamInsightChat({
  chatPayload,
  messages,
  message,
  onToken,
  onDone,
  onError,
}) {
  const res = await fetch(`${BASE}/api/insights/chat`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      chat_payload: chatPayload,
      messages,
      message,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    onError?.(text || `Chat error ${res.status}`);
    return;
  }

  if (!res.body) {
    onError?.("Streaming response body is not available.");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") {
        onDone?.();
        return;
      }
      try {
        const parsed = JSON.parse(payload);
        if (parsed.token) onToken?.(parsed.token);
        if (parsed.error) {
          onError?.(parsed.error);
          return;
        }
      } catch {
        // Skip malformed frames.
      }
    }
  }
  onDone?.();
}

export async function generateReportStream(params, { onEvent, signal } = {}) {
  const res = await fetch(`${BASE}/api/insights/generate/stream`, {
    method: "POST",
    headers: { ...backendAuthedHeaders({ "Content-Type": "application/json" }), ...(await providerKeyHeaders()) },
    body: JSON.stringify(params),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  if (!res.body) {
    throw new Error("Streaming response body is not available.");
  }

  let finalPayload = null;
  let streamError = null;

  await consumeSseStream(res.body, (event) => {
    onEvent?.(event);
    if (event.event === "pipeline_finished") {
      finalPayload = event.payload;
    } else if (event.event === "pipeline_failed") {
      streamError = event.error || "Report generation failed.";
    }
  }, signal);

  if (streamError) throw new Error(streamError);
  if (finalPayload) return finalPayload;
  throw new Error("Stream ended before returning a final report payload.");
}

// ---------------------------------------------------------------------------
// Unified agent session API  (/api/agents)
// ---------------------------------------------------------------------------

/** List all available agent types. */
export async function listAgents() {
  const res = await fetch(`${BASE}/api/agents`, { headers: backendApiHeaders() });
  if (!res.ok) throw new Error(`Failed to list agents: ${res.status}`);
  return res.json();
}

/**
 * Create an agent session and start the pipeline.
 * Returns { session_id, stream_url, agent_type }.
 * Then connect to openAgentStream(agentType, sessionId) for SSE events.
 */
export async function createAgentSession(agentType, params) {
  const res = await fetch(`${BASE}/api/agents/${encodeURIComponent(agentType)}/sessions`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  return res.json(); // { session_id, stream_url, agent_type }
}

/**
 * Open the SSE stream for an active session.
 * Returns the raw ReadableStream body — consume with a reader loop.
 */
export async function openAgentStream(agentType, sessionId, { signal } = {}) {
  const url = `${BASE}/api/agents/${encodeURIComponent(agentType)}/sessions/${encodeURIComponent(sessionId)}/stream`;
  const res = await fetch(url, { headers: backendApiHeaders(), signal });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Stream error ${res.status}`);
  }
  return res.body;
}

/**
 * Send a message into an active agent session.
 *
 * type="chat"   — follow-up text or content blocks with images
 * type="answer" — answer to a pending AskUserQuestion
 */
export async function sendAgentMessage(agentType, sessionId, message) {
  // message: { type: "chat"|"answer", content?, context_version_id?, answers? }
  const res = await fetch(
    `${BASE}/api/agents/${encodeURIComponent(agentType)}/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      headers: backendApiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(message),
    }
  );
  if (!res.ok) throw new Error(`Message failed: ${res.status}`);
  return res.json();
}

/** Close an agent session and free server-side resources. */
export async function closeAgentSession(agentType, sessionId) {
  await fetch(
    `${BASE}/api/agents/${encodeURIComponent(agentType)}/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE", headers: backendApiHeaders() }
  );
}

// ---------------------------------------------------------------------------
// Persisted conversations (chat history / resume)
// ---------------------------------------------------------------------------
//
// All four send the Bearer token, not just the API key. A conversation belongs
// to a project, and the backend gates these on project membership — the shared
// X-API-Key is baked into this bundle and says nothing about who is asking.
// Every caller is inside the signed-in app shell, so a token is always present.

/** List an agent's conversations (resume lookup / history). Returns an array of
 * conversation summaries. Pass filters: { projectId, artifactType, artifactId }.
 * Omitting projectId lists across the caller's own projects. */
export async function listAgentConversations(agentType, { projectId, artifactType, artifactId, includeArchived } = {}) {
  const qs = new URLSearchParams();
  if (projectId) qs.set("project_id", projectId);
  if (artifactType) qs.set("artifact_type", artifactType);
  if (artifactId) qs.set("artifact_id", artifactId);
  if (includeArchived) qs.set("include_archived", "true");
  const res = await fetch(
    `${BASE}/api/agents/${encodeURIComponent(agentType)}/conversations?${qs.toString()}`,
    { headers: backendAuthedHeaders() }
  );
  if (!res.ok) throw new Error(`List conversations failed: ${res.status}`);
  return res.json();
}

/** Fetch a conversation + its event log for UI rehydration.
 * Returns { conversation, events: [{ seq, kind, data, created_at }] }. */
export async function getAgentConversation(agentType, conversationId) {
  const res = await fetch(
    `${BASE}/api/agents/${encodeURIComponent(agentType)}/conversations/${encodeURIComponent(conversationId)}`,
    { headers: backendAuthedHeaders() }
  );
  if (!res.ok) throw new Error(`Get conversation failed: ${res.status}`);
  return res.json();
}

/** Pin (or rename) a conversation. Pinning only changes list order. */
export async function patchAgentConversation(agentType, conversationId, patch) {
  const res = await fetch(
    `${BASE}/api/agents/${encodeURIComponent(agentType)}/conversations/${encodeURIComponent(conversationId)}`,
    {
      method: "PATCH",
      headers: backendAuthedHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(patch),
    }
  );
  if (!res.ok) throw new Error(`Patch conversation failed: ${res.status}`);
  return res.json();
}

/** Archive a conversation (start-fresh support). */
export async function archiveAgentConversation(agentType, conversationId) {
  const res = await fetch(
    `${BASE}/api/agents/${encodeURIComponent(agentType)}/conversations/${encodeURIComponent(conversationId)}/archive`,
    { method: "POST", headers: backendAuthedHeaders() }
  );
  if (!res.ok) throw new Error(`Archive conversation failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Lead magnet
// ---------------------------------------------------------------------------

/**
 * Validate a lead magnet access token.
 * Token is sent in the POST body — not as a query param — to avoid it appearing
 * in server logs, browser history, or Referer headers.
 * Returns { website_url } or throws if the token is invalid / expired.
 */
export async function validateLeadToken(token) {
  const res = await fetch(`${BASE}/api/lead-magnet/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) throw new Error("Invalid or expired lead token");
  return res.json();
}

/**
 * Persist the completed audit report against a lead magnet record.
 * First write wins — 409 means it was already saved (silent success).
 * Never throws; failures are logged but don't disrupt the user's report view.
 */
export async function saveLeadReport(token, report) {
  try {
    await fetch(`${BASE}/api/lead-magnet/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, report }),
    });
  } catch {
    // Fire-and-forget: network errors shouldn't interrupt the user experience
  }
}

/**
 * Record a lead's interest in paid execution (demand-validation test).
 * `services` is an array of keys: "ai_ready_fixes" | "content_rewrites" | "translation".
 * Resolves true on success, throws on failure so the modal can show an error state.
 */
export async function expressExecutionInterest(token, { services, findingIds = null, note = null }) {
  const res = await fetch(`${BASE}/api/lead-magnet/execution-interest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, services, finding_ids: findingIds, note }),
  });
  if (!res.ok) throw new Error("Could not record execution interest");
  return true;
}
