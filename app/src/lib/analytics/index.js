"use client";

/**
 * The analytics seam.
 *
 * Everything above this line decides *whether* to measure — `lib/consent.js`
 * for the rule, `ProductAnalytics` for the flow. Everything below it decides
 * *how*, and names a vendor. Mirrors `desktop/src-tauri/src/telemetry/` on the
 * Rust side, for the same reason: the builds we distribute measure, and a fork
 * should be able to drop that or replace it without reading our consent logic.
 *
 * Selected by `NEXT_PUBLIC_ANALYTICS_PROVIDER`. Unset falls back to `gtm` when
 * a container is configured and `none` otherwise — so an existing deploy keeps
 * its behaviour, and a self-host build that sets neither variable measures
 * nothing without having to opt out of anything.
 *
 * Adding a provider is one file exporting the eight members below, plus a line
 * in `PROVIDERS`. No other file should need to change.
 */

import { gtm } from "./gtm";
import { none } from "./none";

const PROVIDERS = { gtm, none };

function resolve() {
  const requested = process.env.NEXT_PUBLIC_ANALYTICS_PROVIDER;
  if (requested) {
    const chosen = PROVIDERS[requested];
    if (chosen) return chosen;
    // A typo here would otherwise measure nothing and say nothing, which is the
    // failure you find out about a quarter later from an empty dashboard.
    console.warn(
      `[analytics] unknown NEXT_PUBLIC_ANALYTICS_PROVIDER "${requested}" — measuring nothing. ` +
        `Known providers: ${Object.keys(PROVIDERS).join(", ")}.`,
    );
    return none;
  }
  return process.env.NEXT_PUBLIC_GTM_ID ? gtm : none;
}

export const analytics = resolve();

/**
 * Push a custom event. Safe before the provider starts — GTM's dataLayer queues,
 * and a provider that never starts drops it, which is the intent.
 */
export function trackEvent(event, params = {}) {
  if (typeof window === "undefined") return;
  analytics.track(event, params);
}
