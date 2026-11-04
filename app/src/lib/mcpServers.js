/**
 * Pure helpers for showing an MCP server the user connected: where it lives,
 * whose mark to draw for it, why it needs attention, and which MCP Registry
 * results are worth showing beside it. No network, no React, so the
 * Connections page, the approval card and a test all read a server one way.
 */

import { msg } from "@lingui/core/macro";
import { McpProblem, McpServerStatus } from "./connectorsApi";

/** The public page that walks through each preset and the by-address path. */
export const MCP_GUIDE_URL = "https://getduct.ai/mcp";

/** The host a server lives at — `mcp.notion.com` — or "" for a bad address. */
export function serverHost(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

// Subdomains vendors put their MCP endpoint on. The favicon a person
// recognises is the vendor's site, and these hosts rarely serve one.
const ENDPOINT_LABELS = new Set(["mcp", "api", "app", "server", "www"]);

/**
 * The vendor's site for a server address, for its favicon:
 * `https://mcp.notion.com/mcp` → `https://notion.com`.
 *
 * A guess, and a safe one: drop one endpoint-looking label when at least two
 * remain, and let the avatar's monogram stand in when the site has no icon.
 * A preset carries its `home` and never needs this; a server added by URL,
 * or one named in a run's approval card, has only its address.
 */
export function serverSite(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return "";
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return "";
  const labels = parsed.hostname.split(".");
  if (labels.length > 2 && ENDPOINT_LABELS.has(labels[0])) {
    return `${parsed.protocol}//${labels.slice(1).join(".")}`;
  }
  return parsed.origin;
}

/** What a card's status line says after "Needs attention", per problem. */
export const PROBLEM_SHORT = {
  [McpProblem.SIGNED_OUT]: msg`Sign-in expired`,
  [McpProblem.KEY_REFUSED]: msg`Key refused`,
  [McpProblem.AUTH_REQUIRED]: msg`Now asks for a sign-in`,
  [McpProblem.UNREADABLE]: msg`Sign-in lost`,
  [McpProblem.UNREACHABLE]: msg`Not answering`,
  [McpProblem.FAILING]: msg`Returning errors`,
};

/** The same reason said whole, with what fixes it, for the server's dialog. */
export const PROBLEM_DETAIL = {
  [McpProblem.SIGNED_OUT]: msg`Its sign-in expired or was revoked, so Duct can't use it until you reconnect.`,
  [McpProblem.KEY_REFUSED]: msg`It refused the saved API key. Reconnect with a new one to use it again.`,
  [McpProblem.AUTH_REQUIRED]: msg`It connected without a sign-in and now asks for one. Reconnect to sign in.`,
  [McpProblem.UNREADABLE]: msg`Duct can no longer read its saved sign-in. Reconnect to use it again.`,
  [McpProblem.UNREACHABLE]: msg`It didn't answer the last time Duct called it. The next chat tries again, or check it now.`,
  [McpProblem.FAILING]: msg`It answered with an error the last time Duct called it. The next chat tries again, or check it now.`,
};

/**
 * Why a server row needs attention, or "" when it doesn't. A row from a Duct
 * server older than recorded reasons carries a status and no problem; for
 * those, needing a sign-in is the only thing the status could mean.
 */
export function serverProblem(server) {
  if (!server || !server.status || server.status === McpServerStatus.CONNECTED) return "";
  if (PROBLEM_SHORT[server.problem]) return server.problem;
  return server.status === McpServerStatus.FAILING ? McpProblem.UNREACHABLE : McpProblem.SIGNED_OUT;
}

/**
 * MCP Registry results for the catalogue: `shown`, and `more` for behind a
 * button. An address the catalogue already has is dropped (a preset, or a
 * server the person connected), since its own tile is in the results above.
 * Shown is what its publisher runs, in the server's order (Official first);
 * the rest wait, because a gateway nobody can vouch for should be a choice
 * someone makes, not a default they scroll past.
 */
export function arrangeRegistry(listings, knownUrls = []) {
  const known = new Set(knownUrls);
  const fresh = (listings || []).filter((listing) => listing?.url && !known.has(listing.url));
  return {
    shown: fresh.filter((listing) => listing.runs_host),
    more: fresh.filter((listing) => !listing.runs_host),
  };
}

/** Who to name on a registry result's card: the site its address belongs to,
 *  `stripe.com` for `https://mcp.stripe.com`. */
export function listingPublisher(listing) {
  return serverHost(serverSite(listing?.url || "")) || listing?.host || "";
}
