/**
 * Intelligence modes — fetched from the backend API.
 *
 * The backend is the single source of truth. This module provides:
 *   fetchModes()   — fetch all modes + goals from GET /api/insights/modes
 *   getModeByKey() — lookup helper
 *   FALLBACK_MODES — used only when the API is unavailable (e.g. SSR with no backend)
 */

import { BASE } from "./api";

export const DEFAULT_MODE_KEY = "organic_growth";

/**
 * Fetch all intelligence modes from the backend.
 * Returns the modes array, with goals embedded per mode.
 */
export async function fetchModes(options = {}) {
  const res = await fetch(`${BASE}/api/insights/modes`, {
    headers: {
      ...(process.env.NEXT_PUBLIC_DUCT_API_KEY
        ? { "X-API-Key": process.env.NEXT_PUBLIC_DUCT_API_KEY }
        : {}),
    },
    ...options,
  });
  if (!res.ok) throw new Error(`Failed to fetch modes: ${res.status}`);
  const data = await res.json();
  return data.modes ?? [];
}

export function getModeByKey(modes, key) {
  if (!modes || !key) return null;
  return modes.find((m) => m.key === key) ?? null;
}

/**
 * Fallback used when the API is unavailable.
 * Goals are intentionally empty for inactive modes.
 * Organic Growth has minimal goal stubs so the UI doesn't break.
 */
export const FALLBACK_MODES = [
  {
    key: "product_intelligence",
    emoji: "📊",
    label: "Product Intelligence",
    short_label: "Product",
    tagline: "Weekly brief for PMs & growth teams",
    active: false,
    locked_connections: [],
    goals: [],
  },
  {
    key: "organic_growth",
    emoji: "🌱",
    label: "Organic Growth",
    short_label: "Organic",
    tagline: "Automated SEO & content intelligence",
    active: true,
    locked_connections: ["gsc", "ga4"],
    goals: [
      { key: "diagnose_traffic_drop", icon: "🔍", label: "Diagnose traffic drops", description: "Find which queries, pages, or channels lost clicks and impressions." },
      { key: "grow_organic_traffic",  icon: "📈", label: "Grow organic traffic",   description: "Identify top ranking opportunities and pages with untapped potential." },
      { key: "improve_rankings",      icon: "🏆", label: "Improve rankings",       description: "Surface pages stuck on page 2–3 and actionable fixes to move them up." },
      { key: "content_gap_analysis",  icon: "✍️", label: "Content gap analysis",  description: "Find topics your competitors rank for that you're missing entirely." },
      { key: "custom",                icon: "✏️", label: "Custom goal",           description: "Describe your own SEO objective." },
    ],
  },
  {
    key: "paid_ads",
    emoji: "📣",
    label: "Paid Ads Intelligence",
    short_label: "Paid Ads",
    tagline: "Cross-platform brief for performance marketers",
    active: false,
    locked_connections: ["google_ads"],
    goals: [],
  },
  {
    key: "sales_revops",
    emoji: "💼",
    label: "Sales / RevOps",
    short_label: "Sales",
    tagline: "Pipeline & revenue intelligence",
    active: false,
    locked_connections: [],
    goals: [],
  },
  {
    key: "ecommerce_dtc",
    emoji: "🛒",
    label: "E-commerce / DTC",
    short_label: "E-commerce",
    tagline: "ROAS, LTV & retention synthesis",
    active: false,
    locked_connections: [],
    goals: [],
  },
  {
    key: "customer_success",
    emoji: "🤝",
    label: "Customer Success",
    short_label: "CS",
    tagline: "Early churn & health score signals",
    active: false,
    locked_connections: [],
    goals: [],
  },
];
