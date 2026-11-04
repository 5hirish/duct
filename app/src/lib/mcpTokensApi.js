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

/** The agents the setup steps cover, in tab order. */
export const AGENTS = ["claude", "codex", "cursor", "vscode", "opencode"];

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
 * Each client's own shape, from its docs. Claude Code and Codex take CLI
 * commands (Claude Code at user scope, so it works from every repo; Codex's
 * second line opens the browser at once rather than on first use). Cursor and
 * OpenCode read a config file, and OpenCode's `mcp auth` starts the sign-in.
 * VS Code adds a server from its Command Palette, so its snippet is the
 * address itself.
 */
export function agentSetup(url) {
  return {
    claude: `claude mcp add --transport http --scope user duct ${url}`,
    codex: `codex mcp add duct --url ${url}\ncodex mcp login duct`,
    cursor: JSON.stringify({ mcpServers: { duct: { url } } }, null, 2),
    vscode: url,
    opencode: JSON.stringify(
      { $schema: "https://opencode.ai/config.json", mcp: { duct: { type: "remote", url } } },
      null,
      2,
    ),
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
