"use client";

/**
 * The model choices, read from and written to the server.
 *
 * `modelTiers.js` still owns the tier vocabulary and the localStorage copy;
 * this owns the round trip. The two exist together on purpose: the browser
 * copy is what paints the page before the network answers and what a
 * signed-out install runs on, and the server copy is what every run reads —
 * including the scheduled brief, which has no browser at all.
 *
 * When they disagree the server wins. A stale tab that saved a map an hour ago
 * must not overwrite what the user has since chosen on their phone.
 *
 * Every write is a partial: send the one field that changed. A whole-object PUT
 * would let a tab loaded before the switch was flipped write the old value back
 * on the next tier change.
 */

import { BASE } from "./api";
import { authedHeaders, hasAuthToken } from "./authFetch";

const ENDPOINT = `${BASE}/api/user/model-settings`;

/** Fired after a successful save, so other surfaces can re-read. */
export const MODEL_SETTINGS_CHANGED = "duct:model-settings-changed";

export const SETTINGS_DEFAULTS = Object.freeze({
  tiers: {},
  auto_fallback: true,
  engine: "",
});

/**
 * The saved settings, or the defaults.
 *
 * Never throws and never rejects: this gates a settings page, not a run, and a
 * page that fails to paint because a preference endpoint was slow is a worse
 * outcome than a page showing the defaults.
 */
export async function fetchModelSettings() {
  if (!hasAuthToken()) return { ...SETTINGS_DEFAULTS };
  try {
    const res = await fetch(ENDPOINT, { headers: authedHeaders() });
    if (!res.ok) return { ...SETTINGS_DEFAULTS };
    const body = await res.json();
    return {
      tiers: body?.tiers && typeof body.tiers === "object" ? body.tiers : {},
      auto_fallback: body?.auto_fallback !== false,
      engine: String(body?.engine || ""),
    };
  } catch {
    return { ...SETTINGS_DEFAULTS };
  }
}

/**
 * Persist the fields given. Returns what the server now holds, or null when it
 * could not be reached — the caller keeps its optimistic state and says so.
 */
export async function saveModelSettings(patch) {
  if (!hasAuthToken()) return null;
  try {
    const res = await fetch(ENDPOINT, {
      method: "PUT",
      headers: { ...authedHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(patch || {}),
    });
    if (!res.ok) return null;
    const body = await res.json();
    window.dispatchEvent(new CustomEvent(MODEL_SETTINGS_CHANGED, { detail: body }));
    return body;
  } catch {
    return null;
  }
}
