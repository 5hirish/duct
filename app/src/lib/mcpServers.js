/**
 * Pure helpers for showing an MCP server the user connected: where it lives
 * and whose mark to draw for it. No network, no React, so the Connections
 * page, the approval card and a test all read a server address one way.
 */

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
