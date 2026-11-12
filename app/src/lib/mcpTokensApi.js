"use client";

// Duct's MCP server from the app's side: the address an agent connects to,
// what to paste into each agent, the consent page's calls when an agent signs
// in through the browser, and the personal tokens and connected agents the
// person manages (/api/user/mcp-tokens).
//
// No localStorage mirror, like membersApi.js: a token list is something only
// the server can be right about, and the plaintext of a new token exists once,
// in the response that minted it. It is never stored here either.

import { BASE } from "./api";
import { authedRequest } from "./authFetch";

const TOKENS_PATH = "/api/user/mcp-tokens";
const REQUESTS_PATH = "/api/oauth/requests";

/** `kind` on a listed row: signed in through the browser, or a pasted token. */
export const KIND_AGENT = "agent";
export const KIND_TOKEN = "token";

/** Where the consent page says the browser returns after Allow. */
export const DESTINATION_DEVICE = "device";
export const DESTINATION_WEB = "web";
export const DESTINATION_APP = "app";

/** The agents the setup steps cover, in picker order. */
export const AGENTS = ["claude", "codex", "cursor", "vscode", "opencode"];

/** Product names, never translated (`keep` in scripts/i18n/glossary.json). */
export const AGENT_NAMES = {
  claude: "Claude Code",
  codex: "Codex",
  cursor: "Cursor",
  vscode: "VS Code",
  opencode: "OpenCode",
};

// What each agent registers itself as when it signs in (its OAuth
// `client_name`), loosely: "Claude Code (duct)", "Visual Studio Code",
// "opencode". First match wins, so Claude Code is tested before anything
// that could contain "code".
const AGENT_NAME_PATTERNS = [
  ["claude", /claude[\s-]?code/i],
  ["vscode", /visual studio code|\bvs ?code\b/i],
  ["opencode", /open ?code/i],
  ["cursor", /\bcursor\b/i],
  ["codex", /\bcodex\b/i],
];

// Claude Code registers as "<product> (<server name>)", so every agent added
// as `duct` would read "Claude Code (duct)" on the consent page and in the
// list, naming us back to ourselves.
const OWN_NAME_SUFFIX = /\s*\(duct\)\s*$/i;

/** The name to show for an agent: the one it gave itself, without our own
 *  server name tacked on. Never more than that, since the name is all the
 *  person has to recognise the agent by. */
export function agentDisplayName(name) {
  return (name || "").replace(OWN_NAME_SUFFIX, "").trim();
}

/** Which agent a connected row is, from the name it gave itself, or null.
 *  Only ever used to pick a logo: the name is self-chosen, so nothing about
 *  access depends on it (the consent page says the same). */
export function agentFromName(name) {
  if (!name) return null;
  const hit = AGENT_NAME_PATTERNS.find(([, pattern]) => pattern.test(name));
  return hit ? hit[0] : null;
}

/** Where an agent sends its requests. Read at call time: the desktop shell
 *  repoints BASE at boot (see api.js). */
export function mcpServerUrl() {
  return `${BASE}/mcp`;
}

export function listMcpTokens() {
  return authedRequest(TOKENS_PATH);
}

/** Resolves to the new token row, with `token` set: the only copy there is. */
export function createMcpToken(name) {
  return authedRequest(TOKENS_PATH, { method: "POST", body: { name } });
}

export function revokeMcpToken(id) {
  return authedRequest(`${TOKENS_PATH}/${id}`, { method: "DELETE" });
}

/**
 * What to paste into each agent to add Duct by address alone. No secret: the
 * agent finds Duct's sign-in from the server's first 401 and opens the
 * browser itself.
 *
 * Each client's own shape, from its docs, and every one of them global, so
 * one setup works from every repo (the page promises that). Claude Code,
 * Codex and OpenCode take CLI commands: Claude Code at user scope, OpenCode
 * with `--global` (it writes to the project's config without it), and the
 * second line of the other two opens the browser at once rather than on
 * first use. Cursor reads `~/.cursor/mcp.json`. VS Code adds a server from
 * its Command Palette, so its snippet is the address itself.
 *
 * OpenCode was a config snippet until November 2026, when its config moved
 * remote servers under `mcp.servers`; its CLI writes whichever shape the
 * installed version reads, which a pasted snippet cannot.
 */
export function agentSetup(url) {
  return {
    claude: `claude mcp add --transport http --scope user duct ${url}`,
    codex: `codex mcp add duct --url ${url}\ncodex mcp login duct`,
    cursor: JSON.stringify({ mcpServers: { duct: { url } } }, null, 2),
    vscode: url,
    opencode: `opencode mcp add duct --global --url ${url}\nopencode mcp auth duct`,
  };
}

/**
 * One-click installs, for the two agents that register a URL handler for it.
 * Both open the agent on its own "add this server?" screen, so nothing is
 * installed without a second click there. Formats from each vendor's docs:
 * Cursor takes the mcp.json entry base64-encoded, VS Code the server's JSON
 * URL-encoded, with its name inside.
 */
export function installLinks(url) {
  const cursorConfig = btoa(JSON.stringify({ url }));
  const vscodeConfig = JSON.stringify({ name: "duct", type: "http", url });
  return {
    cursor: `cursor://anysphere.cursor-deeplink/mcp/install?name=duct&config=${encodeURIComponent(cursorConfig)}`,
    vscode: `vscode:mcp/install?${encodeURIComponent(vscodeConfig)}`,
  };
}

/**
 * For an agent that cannot open a browser (CI, a remote machine): the same
 * address with a personal token as a bearer header. Claude Code's command,
 * and the header itself for anything else.
 */
export function tokenSetup(url, token) {
  const bearer = `Bearer ${token}`;
  return {
    claude: `claude mcp add --transport http --scope user duct ${url} --header "Authorization: ${bearer}"`,
    header: `Authorization: ${bearer}`,
  };
}

/** The agent's sign-in request the consent page was opened with: who it says
 *  it is, and where the browser goes after Allow. Works signed out. */
export function fetchSignInRequest(code) {
  return authedRequest(`${REQUESTS_PATH}/${encodeURIComponent(code)}`);
}

/** Resolves to `{ redirect_to }`: the address to send the browser to, which
 *  hands the agent its code. Needs the signed-in person. */
export function allowSignInRequest(code) {
  return authedRequest(`${REQUESTS_PATH}/${encodeURIComponent(code)}/approve`, { method: "POST" });
}

/** Resolves to `{ redirect_to }`, which tells the agent the person declined. */
export function declineSignInRequest(code) {
  return authedRequest(`${REQUESTS_PATH}/${encodeURIComponent(code)}/deny`, { method: "POST" });
}
