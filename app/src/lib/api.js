const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
