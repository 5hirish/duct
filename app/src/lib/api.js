const configuredBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const normalizedConfiguredBase = configuredBase?.replace(/\/+$/, "");
const isProduction = process.env.NODE_ENV === "production";

/**
 * In production, require an explicit API base URL.
 * This prevents silently sending real users to localhost when env vars are missing.
 */
export const BASE =
  normalizedConfiguredBase || (isProduction ? "" : "http://localhost:8000");

/** Must match backend DUCT_API_KEY. Prefer a Next server proxy in production so this is not public. */
function backendApiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = process.env.NEXT_PUBLIC_DUCT_API_KEY;
  if (key) {
    headers["X-API-Key"] = key;
  }
  return headers;
}

export async function fetchConnectorAccounts(connectorId, refreshToken) {
  const res = await fetch(
    `${BASE}/api/connectors/${encodeURIComponent(connectorId)}/accounts?refresh_token=${encodeURIComponent(refreshToken)}`,
    { headers: backendApiHeaders() }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  const payload = await res.json();
  return payload.accounts ?? [];
}

export async function fetchGoogleAdsAccounts(refreshToken) {
  return fetchConnectorAccounts("google_ads", refreshToken);
}

export async function fetchGa4Properties(refreshToken) {
  return fetchConnectorAccounts("ga4", refreshToken);
}

export async function fetchGscSites(refreshToken) {
  return fetchConnectorAccounts("gsc", refreshToken);
}

export async function generateReport(params) {
  const res = await fetch(`${BASE}/api/generate`, {
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

export async function refreshReportBriefs(routine) {
  const refreshToken = sessionStorage.getItem("gads_refresh_token") || "";
  const ga4RefreshToken = sessionStorage.getItem("ga4_refresh_token") || "";
  const gscRefreshToken = sessionStorage.getItem("gsc_refresh_token") || "";
  const body = {
    connections: routine?.connections || [],
    date_preset: routine?.date_preset || "30",
    date_from: routine?.custom_date_from || "",
    date_to: routine?.custom_date_to || "",
    refresh_token: refreshToken,
    ga4_refresh_token: ga4RefreshToken,
    gsc_refresh_token: gscRefreshToken,
    targets: routine?.targets || {},
  };
  const res = await fetch(`${BASE}/api/reports/refresh`, {
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
  const res = await fetch(`${BASE}/api/generate/stream`, {
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
