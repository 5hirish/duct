/**
 * "How many sources are connected?" — the rule, with no IO.
 *
 * Kept dependency-free so `scripts/check-connector-count.mjs` can load it in
 * bare node, the same way slideDoc.js is loaded by the parity script.
 *
 * The sidebar badge used to count two hardcoded sessionStorage keys (GA4 and
 * GSC), so it could never read past 2 and never saw Google Ads, GTM, or any of
 * the twelve server-stored connector types. The rule below is what replaced
 * that, and it exists as its own function because "the badge and the
 * Connections page disagree" is the bug class worth pinning down.
 */

/** Google OAuth connectors whose refresh token can live in sessionStorage
 *  alone (signed out, or before the durable sync lands). Mirrors the storage
 *  keys the Connections page writes. */
export const SESSION_TOKEN_KEYS = {
  google_ads: "gads_refresh_token",
  ga4: "ga4_refresh_token",
  gsc: "gsc_refresh_token",
  gtm: "gtm_refresh_token",
};

/**
 * @param sessionTypes   connector types with a refresh token in this browser
 * @param serverTypes    connector types with a stored credential row (repeats
 *                       per account — two Stripe accounts are one source)
 * @param hasAdsDevToken whether the user's Google Ads developer token is present
 * @returns the distinct connector types that count as connected
 */
export function resolveConnectedTypes({
  sessionTypes = [],
  serverTypes = [],
  hasAdsDevToken = false,
} = {}) {
  const types = new Set([...sessionTypes, ...serverTypes].filter(Boolean));
  // Google Ads needs the user's own developer token as well as OAuth, and that
  // token lives outside both sources above (OS keychain on desktop, session
  // storage on web — see lib/adsCredentials.js). The Connections page calls it
  // "partial" without one, so counting it here would put the badge back in
  // disagreement with the page, which is the bug this replaced.
  if (!hasAdsDevToken) types.delete("google_ads");
  return types;
}
