// The three snippets are a contract with three other programs' config
// formats. Each assertion is the part that, if wrong, connects nothing.

import { describe, expect, it } from "vitest";
import { agentSnippets } from "../mcpTokensApi";

const URL_ = "https://api.example.com/mcp";
const TOKEN = "duct_mcp_example";

describe("agentSnippets", () => {
  const snippets = agentSnippets(URL_, TOKEN);

  it("adds Duct to Claude Code for every repo, over HTTP, with the token as a header", () => {
    expect(snippets.claude).toBe(
      `claude mcp add --transport http --scope user duct ${URL_} --header "Authorization: Bearer ${TOKEN}"`,
    );
  });

  it("gives Codex a table it accepts: a url and a static header, never bearer_token", () => {
    expect(snippets.codex.split("\n")).toEqual([
      "[mcp_servers.duct]",
      `url = "${URL_}"`,
      `http_headers = { Authorization = "Bearer ${TOKEN}" }`,
    ]);
  });

  it("gives Cursor valid mcp.json", () => {
    expect(JSON.parse(snippets.cursor)).toEqual({
      mcpServers: { duct: { url: URL_, headers: { Authorization: `Bearer ${TOKEN}` } } },
    });
  });
});
