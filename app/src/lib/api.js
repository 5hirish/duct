export const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Must match backend DUCT_API_KEY. Prefer a Next server proxy in production so this is not public. */
function backendApiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = process.env.NEXT_PUBLIC_DUCT_API_KEY;
  if (key) {
    headers["X-API-Key"] = key;
  }
  return headers;
}

export async function fetchGoogleAdsAccounts(refreshToken) {
  const res = await fetch(
    `${BASE}/api/connectors/google_ads/accounts?refresh_token=${encodeURIComponent(refreshToken)}`,
    { headers: backendApiHeaders() }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  const payload = await res.json();
  return payload.accounts ?? [];
}

export async function runGoogleAdsReport(params) {
  const res = await fetch(`${BASE}/api/report/google-ads`, {
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
