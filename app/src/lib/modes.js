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
    business_context_fields: [],
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
    business_context_fields: [
      {
        key: "primary_organic_kpi",
        label: "Primary organic KPI",
        type: "select",
        placeholder: "Select primary KPI...",
        options: [
          { value: "organic_traffic", label: "Organic Traffic" },
          { value: "keyword_rankings", label: "Keyword Rankings" },
          { value: "backlinks", label: "Backlinks" },
          { value: "conversions_from_organic", label: "Conversions from Organic" },
        ],
      },
      {
        key: "monthly_organic_traffic_target",
        label: "Monthly organic traffic target (optional)",
        type: "number",
        placeholder: "e.g. 10000",
        min: 0,
        step: 1,
        empty_if_zero: true,
      },
      {
        key: "primary_content_type",
        label: "Primary content type",
        type: "select",
        placeholder: "Select content type...",
        options: [
          { value: "blog_articles", label: "Blog/Articles" },
          { value: "product_pages", label: "Product Pages" },
          { value: "landing_pages", label: "Landing Pages" },
          { value: "docs_help", label: "Docs/Help" },
        ],
      },
      {
        key: "period_changes",
        label: "What changed recently? (optional)",
        type: "textarea",
        placeholder: "e.g. Published 10 new articles, migrated to new CMS, added hreflang tags.",
        rows: 2,
        full_width: true,
      },
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
    business_context_fields: [
      {
        key: "industry",
        label: "Industry",
        type: "select",
        placeholder: "Select industry...",
        options: [
          { value: "ecommerce", label: "E-commerce" },
          { value: "saas", label: "SaaS / B2B" },
          { value: "lead_gen", label: "Lead generation" },
          { value: "agency", label: "Agency / multi-client" },
          { value: "other", label: "Other" },
        ],
        show_if: "always",
      },
      {
        key: "primary_conversion_action",
        label: "Primary conversion action",
        type: "text",
        placeholder: "e.g. Demo booked, Trial started, Purchase",
        show_if: "ads_selected",
      },
      {
        key: "monthly_budget",
        label: "Monthly budget ($)",
        type: "number",
        placeholder: "e.g. 5000",
        min: 0,
        step: 0.01,
        show_if: "ads_selected",
      },
      {
        key: "target_cpa",
        label: "Target CPA ($)",
        type: "number",
        placeholder: "e.g. 50",
        min: 0,
        step: 0.01,
        show_if: "ads_selected",
      },
      {
        key: "target_roas",
        label: "Target ROAS (x)",
        type: "number",
        placeholder: "e.g. 3.0",
        min: 0,
        step: 0.1,
        show_if: "ads_selected",
      },
      {
        key: "target_payback_days",
        label: "Target payback (days)",
        type: "number",
        placeholder: "e.g. 90",
        min: 0,
        step: 1,
        show_if: "ads_selected",
      },
      {
        key: "gross_margin_percent",
        label: "Gross margin (%)",
        type: "number",
        placeholder: "e.g. 70",
        min: 0,
        max: 100,
        step: 1,
        show_if: "ads_selected",
      },
      {
        key: "qualified_lead_value",
        label: "Qualified lead value ($)",
        type: "number",
        placeholder: "e.g. 1200",
        min: 0,
        step: 1,
        show_if: "ads_selected",
      },
      {
        key: "period_changes",
        label: "What changed during this period? (optional)",
        type: "textarea",
        placeholder: "e.g. Switched bid strategy, launched new offer, changed landing pages, tracking updates.",
        rows: 2,
        full_width: true,
        show_if: "ads_selected",
      },
    ],
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
    business_context_fields: [],
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
    business_context_fields: [],
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
    business_context_fields: [],
  },
];
