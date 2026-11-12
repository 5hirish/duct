// The snippets are a contract with other programs' config formats and CLIs.
// Each assertion is the part that, if wrong, connects nothing.

import { describe, expect, it } from "vitest";
import { AGENTS, AGENT_NAMES, agentDisplayName, agentFromName, agentSetup, installLinks, tokenSetup } from "../mcpTokensApi";

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

  it("adds Duct to OpenCode for every project and starts its sign-in", () => {
    expect(setup.opencode.split("\n")).toEqual([
      `opencode mcp add duct --global --url ${URL_}`,
      "opencode mcp auth duct",
    ]);
  });

  it("never carries a token", () => {
    expect(Object.values(setup).join("\n")).not.toMatch(/duct_mcp_|Bearer/);
  });
});

describe("installLinks", () => {
  const links = installLinks(URL_);

  it("hands Cursor its mcp.json entry, base64-encoded, under the name duct", () => {
    const link = new globalThis.URL(links.cursor);
    expect(link.protocol).toBe("cursor:");
    expect(link.searchParams.get("name")).toBe("duct");
    expect(JSON.parse(atob(link.searchParams.get("config")))).toEqual({ url: URL_ });
  });

  it("hands VS Code an HTTP server named duct, URL-encoded", () => {
    const [scheme, query] = links.vscode.split("?");
    expect(scheme).toBe("vscode:mcp/install");
    expect(JSON.parse(decodeURIComponent(query))).toEqual({ name: "duct", type: "http", url: URL_ });
  });
});

describe("agentFromName", () => {
  it("names every agent the picker shows by the name it gives itself", () => {
    expect(Object.keys(AGENT_NAMES).sort()).toEqual([...AGENTS].sort());
    expect(agentFromName("Claude Code (duct)")).toBe("claude");
    expect(agentFromName("Visual Studio Code")).toBe("vscode");
    expect(agentFromName("opencode")).toBe("opencode");
    expect(agentFromName("Cursor")).toBe("cursor");
    expect(agentFromName("codex-mcp-client")).toBe("codex");
  });

  it("leaves an agent it does not know without a logo", () => {
    expect(agentFromName("My CI runner")).toBeNull();
    expect(agentFromName("")).toBeNull();
  });
});

describe("agentDisplayName", () => {
  it("drops our own server name that Claude Code appends, and nothing else", () => {
    expect(agentDisplayName("Claude Code (duct)")).toBe("Claude Code");
    expect(agentDisplayName("Cursor")).toBe("Cursor");
    expect(agentDisplayName("Claude Code (work laptop)")).toBe("Claude Code (work laptop)");
    expect(agentDisplayName(undefined)).toBe("");
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
