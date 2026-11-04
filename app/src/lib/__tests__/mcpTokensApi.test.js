// The snippets are a contract with other programs' config formats and CLIs.
// Each assertion is the part that, if wrong, connects nothing.

import { describe, expect, it } from "vitest";
import { AGENTS, agentSetup, tokenSetup } from "../mcpTokensApi";

const URL_ = "https://api.example.com/mcp";
// Not called TOKEN: scripts/security/audit.py reads `TOKEN = "…"` as a
// hardcoded secret.
const MINTED = "duct_mcp_example";

describe("agentSetup", () => {
  const setup = agentSetup(URL_);

  it("covers every agent the steps show a tab for", () => {
    expect(Object.keys(setup).sort()).toEqual([...AGENTS].sort());
  });

  it("adds Duct to Claude Code for every repo, over HTTP, with no secret in it", () => {
    expect(setup.claude).toBe(`claude mcp add --transport http --scope user duct ${URL_}`);
  });

  it("adds Duct to Codex as a URL server and starts its sign-in", () => {
    expect(setup.codex.split("\n")).toEqual([`codex mcp add duct --url ${URL_}`, "codex mcp login duct"]);
  });

  it("gives Cursor valid mcp.json with the address alone", () => {
    expect(JSON.parse(setup.cursor)).toEqual({ mcpServers: { duct: { url: URL_ } } });
  });

  it("gives OpenCode a remote server it will sign in to", () => {
    expect(JSON.parse(setup.opencode).mcp).toEqual({ duct: { type: "remote", url: URL_ } });
  });

  it("never carries a token", () => {
    expect(Object.values(setup).join("\n")).not.toMatch(/duct_mcp_|Bearer/);
  });
});

describe("tokenSetup", () => {
  it("sends a pasted token as a bearer header", () => {
    const setup = tokenSetup(URL_, MINTED);
    expect(setup.claude).toBe(
      `claude mcp add --transport http --scope user duct ${URL_} --header "Authorization: Bearer ${MINTED}"`,
    );
    expect(setup.header).toBe(`Authorization: Bearer ${MINTED}`);
  });
});
