"use client";

// Lends this device's provider keys to memory consolidation while the app is
// open. Duct turns finished conversations into project memory in the
// background, and background work can only spend a key the server has: a saved
// one, or one a live request carries. Keys kept in the desktop keychain (or a
// browser tab) are never saved, so without this their owner's conversations are
// never consolidated. The backend picks what is due and scopes it to projects
// the caller owns (POST /api/user/memory/catch-up); this only says "my keys are
// here now".

import { authedFetch, authToken } from "./authFetch";
import { PROVIDERS, getProviderKey } from "./providerKeys";

/** How often an open app offers its keys. Matches the backend's idle window. */
export const CATCH_UP_INTERVAL_MS = 30 * 60 * 1000;

/**
 * The API-key headers only. A ChatGPT sign-in is deliberately absent: the
 * backend cannot spend a plan token on this call, and fetching one refreshes
 * it for nothing.
 */
export async function apiKeyHeaders() {
  const headers = {};
  for (const provider of PROVIDERS) {
    const key = await getProviderKey(provider.id);
    if (key) headers[provider.header] = key;
  }
  return headers;
}

/** One offer. Silent: a missed catch-up is retried next interval. */
export async function catchUpMemory() {
  if (!authToken()) return false;
  const headers = await apiKeyHeaders();
  if (Object.keys(headers).length === 0) return false;
  try {
    const res = await authedFetch("/api/user/memory/catch-up", {
      method: "POST",
      headers,
      retireSession: false,
    });
    return Boolean((await res.json())?.scheduled);
  } catch {
    return false;
  }
}

/**
 * Offer now and every interval while the page is visible. Returns the stop
 * function for an effect's cleanup.
 */
export function startMemoryCatchUp({ interval = CATCH_UP_INTERVAL_MS } = {}) {
  if (typeof window === "undefined") return () => {};
  const tick = () => {
    if (document.visibilityState === "visible") catchUpMemory();
  };
  tick();
  const timer = window.setInterval(tick, interval);
  return () => window.clearInterval(timer);
}
