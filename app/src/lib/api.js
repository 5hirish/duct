export const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function fetchGoogleAdsAccounts(refreshToken) {
  const res = await fetch(
    `${BASE}/api/google-ads/accounts?refresh_token=${encodeURIComponent(refreshToken)}`
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error ${res.status}`);
  }
  return res.json();
}
