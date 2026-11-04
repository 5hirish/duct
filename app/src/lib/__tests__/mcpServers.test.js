import { describe, expect, it } from "vitest";
import { McpProblem, McpServerStatus } from "../connectorsApi";
import {
  PROBLEM_DETAIL,
  PROBLEM_SHORT,
  arrangeRegistry,
  listingPublisher,
  serverHost,
  serverProblem,
  serverSite,
} from "../mcpServers";
import { FIGMA_LISTINGS, GATEWAY_ONLY_LISTINGS, STRIPE_LISTINGS } from "../__fixtures__/mcpRegistry.mjs";

describe("serverSite", () => {
  it("finds the vendor's site behind an endpoint subdomain", () => {
    expect(serverSite("https://mcp.notion.com/mcp")).toBe("https://notion.com");
    expect(serverSite("https://app.openseo.so/mcp")).toBe("https://openseo.so");
    expect(serverSite("https://mcp.linear.app/mcp")).toBe("https://linear.app");
  });

  it("leaves a host it has no reason to shorten alone, port included", () => {
    expect(serverSite("https://tools.example.com/mcp")).toBe("https://tools.example.com");
    expect(serverSite("https://mcp.io/sse")).toBe("https://mcp.io");
    expect(serverSite("http://localhost:8080/mcp")).toBe("http://localhost:8080");
  });

  it("returns nothing for an address it cannot read", () => {
    expect(serverSite("not a url")).toBe("");
    expect(serverSite("ftp://mcp.example.com")).toBe("");
  });
});

describe("serverHost", () => {
  it("is the host alone, or empty", () => {
    expect(serverHost("https://mcp.posthog.com/mcp")).toBe("mcp.posthog.com");
    expect(serverHost("")).toBe("");
  });
});

describe("serverProblem", () => {
  it("is empty for a server that works, or none at all", () => {
    expect(serverProblem(null)).toBe("");
    expect(serverProblem({ status: McpServerStatus.CONNECTED, problem: "" })).toBe("");
  });

  it("is the recorded reason when there is one", () => {
    expect(serverProblem({ status: McpServerStatus.NEEDS_REAUTH, problem: McpProblem.KEY_REFUSED })).toBe(
      McpProblem.KEY_REFUSED,
    );
    expect(serverProblem({ status: McpServerStatus.FAILING, problem: McpProblem.FAILING })).toBe(McpProblem.FAILING);
  });

  it("reads a row from an older Duct, which has a status and no reason", () => {
    expect(serverProblem({ status: McpServerStatus.NEEDS_REAUTH })).toBe(McpProblem.SIGNED_OUT);
    expect(serverProblem({ status: McpServerStatus.FAILING, problem: "something new" })).toBe(McpProblem.UNREACHABLE);
  });

  it("has words for every reason the server records", () => {
    for (const problem of Object.values(McpProblem)) {
      expect(PROBLEM_SHORT[problem]).toBeTruthy();
      expect(PROBLEM_DETAIL[problem]).toBeTruthy();
    }
  });
});

describe("arrangeRegistry", () => {
  it("shows what its publisher runs, vendor's own first, and holds the rest back", () => {
    const { shown, more } = arrangeRegistry(STRIPE_LISTINGS);
    expect(shown[0].official).toBe(true);
    expect(shown.every((l) => l.runs_host)).toBe(true);
    expect(more.map((l) => l.url)).toEqual(["https://stripe.insightfulmcp.com/", "https://api.mcp.ai/p_stripe"]);
  });

  it("drops an address the catalogue already has a tile for", () => {
    const { shown } = arrangeRegistry(STRIPE_LISTINGS, ["https://mcp.stripe.com"]);
    expect(shown.some((l) => l.url === "https://mcp.stripe.com")).toBe(false);
  });

  it("can show nothing and still hold servers back", () => {
    const { shown, more } = arrangeRegistry(GATEWAY_ONLY_LISTINGS);
    expect(shown).toEqual([]);
    expect(more).toHaveLength(2);
  });

  it("names the site an address belongs to", () => {
    expect(listingPublisher(STRIPE_LISTINGS[0])).toBe("stripe.com");
    expect(listingPublisher(FIGMA_LISTINGS[1])).toBe("agent-observatory-sensor.nolimit-observatory.workers.dev");
  });
});
