import { googleAdsByoCredentials } from "./adsCredentials";

const configuredBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const normalizedConfiguredBase = configuredBase?.replace(/\/+$/, "");
const isProduction = process.env.NODE_ENV === "production";

/**
 * In production, require an explicit API base URL.
 * This prevents silently sending real users to localhost when env vars are missing.
 */
export const BASE =
  normalizedConfiguredBase || (isProduction ? "" : "http://localhost:8002");

/** Must match backend DUCT_API_KEY. Prefer a Next server proxy in production so this is not public. */
function backendApiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = process.env.NEXT_PUBLIC_DUCT_API_KEY;
  if (key) {
    headers["X-API-Key"] = key;
  }
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

export async function generateReport(params) {
  const res = await fetch(`${BASE}/api/insights/generate`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
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

function parseSseFrames(buffer) {
  const frames = [];
  let rest = buffer;
  let splitIndex = rest.indexOf("\n\n");
  while (splitIndex !== -1) {
    const frame = rest.slice(0, splitIndex);
    rest = rest.slice(splitIndex + 2);
    frames.push(frame);
    splitIndex = rest.indexOf("\n\n");
  }
  return { frames, rest };
}

function parseSseDataFrame(frame) {
  const lines = frame.split("\n");
  const dataLines = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .filter(Boolean);
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
}

export async function generateReportStream(params, { onEvent, signal } = {}) {
  const res = await fetch(`${BASE}/api/insights/generate/stream`, {
    method: "POST",
    headers: backendApiHeaders({ "Content-Type": "application/json" }),
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

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = null;
  let streamError = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseFrames(buffer);
    buffer = parsed.rest;

    for (const frame of parsed.frames) {
      const event = parseSseDataFrame(frame);
      if (!event) continue;
      onEvent?.(event);
      if (event.event === "pipeline_finished") {
        finalPayload = event.payload;
      } else if (event.event === "pipeline_failed") {
        streamError = event.error || "Report generation failed.";
      }
    }
  }

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
