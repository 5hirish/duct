"use client";

// What Duct has spent on your provider key.
//
// Server-only, with no localStorage mirror, for the same reason lib/membersApi
// has none: this is money, and a stale figure is worse than a spinner. The
// backend scopes every row to the caller, so there is nothing to filter here.

import { BASE } from "./api";
import { authedHeaders as headers } from "./authFetch";

/** Windows the page offers. Kept here so the page and the API agree on one list. */
export const WINDOWS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
];

export const DEFAULT_WINDOW_DAYS = 30;

/** Empty shape, so a page can render its own layout before the first response. */
export const EMPTY_USAGE = Object.freeze({
  window_days: DEFAULT_WINDOW_DAYS,
  total: { calls: 0, input_tokens: 0, output_tokens: 0, cached_tokens: 0, total_tokens: 0, cost_usd: 0 },
  by_agent: [],
  by_model: [],
  by_provider: [],
  daily: [],
});

export async function fetchUsage({ windowDays = DEFAULT_WINDOW_DAYS, projectId = "" } = {}) {
  const params = new URLSearchParams({ window_days: String(windowDays) });
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${BASE}/api/user/usage?${params}`, { headers: headers() });
  if (!res.ok) throw new Error(`Could not load usage (${res.status})`);
  return res.json();
}

/**
 * Agent keys are the backend's internal names; these are what a user calls them.
 * An unmapped key falls back to itself rather than to "Unknown" — a new agent
 * should look unpolished here, not anonymous.
 */
const AGENT_LABELS = {
  insights: "Organic Growth",
  audit: "SEO Audit",
  content: "Content Studio",
  tiktok_studio: "Content Studio",
};

export function agentLabel(key) {
  return AGENT_LABELS[key] || key || "Other";
}

const PROVIDER_LABELS = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google_genai: "Google",
  openrouter: "OpenRouter",
  xai: "xAI",
};

export function providerLabel(key) {
  return PROVIDER_LABELS[key] || key || "Other";
}

/**
 * Money, at the precision the number deserves.
 *
 * Sub-cent totals are the normal case on a light week, and rendering one as
 * "$0.00" reads as "this is free" — which is the opposite of what this page
 * exists to say. Null stays null: the caller shows tokens instead.
 */
export function formatCost(usd) {
  if (usd === null || usd === undefined) return null;
  if (usd === 0) return "$0";
  if (usd < 0.01) return "<$0.01";
  if (usd < 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

/** Tokens, compact. 1.2M reads; 1204338 does not. */
export function formatTokens(n) {
  const value = Number(n) || 0;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(value);
}

/** Each row's share of the total, for the bars. Guards the empty-week divide. */
export function share(value, total) {
  const t = Number(total) || 0;
  if (!t) return 0;
  return Math.max(0, Math.min(1, (Number(value) || 0) / t));
}
