"use client";

// What the composer's thinking picker offers, asked of the server.
//
// The mapping from Duct's four rungs to each provider's own words lives in
// backend/agents/thinking.py and is NOT mirrored here. It depends on the model
// the engine resolves to, which is config the browser does not have — and a
// picker offering a rung the API would reject is worse than no picker.

import { BASE } from "./api";
import { authedHeaders } from "./authFetch";

/** Nothing on offer — the shape a caller gets when the model has no dial. */
export const NO_THINKING = Object.freeze({ supported: false, levels: [], dial: "" });

/**
 * Levels available on the model this engine would use.
 * Never throws: the composer must render whether or not this resolves.
 */
export async function fetchThinking(engineKey) {
  try {
    const qs = engineKey ? `?engine=${encodeURIComponent(engineKey)}` : "";
    const res = await fetch(`${BASE}/api/engines/thinking${qs}`, {
      headers: authedHeaders(),
    });
    if (!res.ok) return NO_THINKING;
    const body = await res.json();
    return body?.supported ? body : NO_THINKING;
  } catch {
    return NO_THINKING;
  }
}

/**
 * The secondary line on a menu row: what the provider will actually be sent,
 * and whether that is what it would have done anyway.
 *
 * Naming the native value is the honesty clause — the abstraction saves the
 * user from learning five dialects, it does not hide which one is in use.
 */
export function levelHint(level, dial) {
  const parts = [`${dial || "effort"} ${level.native}`];
  if (level.is_default) parts.push("default");
  if (level.same_as) parts.push(`same as ${level.same_as}`);
  return parts.join(" · ");
}
