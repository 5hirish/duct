"use client";

// Personal tokens for Duct's MCP server (/api/user/mcp-tokens), and the
// address an agent connects to.
//
// No localStorage mirror, like membersApi.js: a token list is something only
// the server can be right about, and the plaintext of a new token exists once,
// in the response that minted it. It is never stored here either.

import { BASE } from "./api";
import { authedRequest } from "./authFetch";

const TOKENS_PATH = "/api/user/mcp-tokens";

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
 * What to paste into each agent, with the token filled in when there is one.
 *
 * Each client's own shape, from its docs: Claude Code takes a CLI command
 * (user scope, so it works from every repo), Codex a `config.toml` table, and
 * Cursor its `mcp.json`. All three send the token as a bearer header.
 */
export function agentSnippets(url, token) {
  const bearer = `Bearer ${token}`;
  return {
    claude: `claude mcp add --transport http --scope user duct ${url} --header "Authorization: ${bearer}"`,
    codex: `[mcp_servers.duct]\nurl = "${url}"\nhttp_headers = { Authorization = "${bearer}" }`,
    cursor: JSON.stringify(
      { mcpServers: { duct: { url, headers: { Authorization: bearer } } } },
      null,
      2,
    ),
  };
}
