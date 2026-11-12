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
 *
 * Stored rows are the only source. The Google connectors used to count a
 * refresh token held in this tab's session storage as well, which is how a
 * badge read "connected" in one tab and "not connected" in the next: the token
 * no longer reaches the browser at all (issue #456).
 */

/**
 * @param serverTypes connector types with a stored credential row (repeats
 *                    per account — two Stripe accounts are one source)
 * @returns the distinct connector types that count as connected
 */
export function resolveConnectedTypes({ serverTypes = [] } = {}) {
  return new Set(serverTypes.filter(Boolean));
}
