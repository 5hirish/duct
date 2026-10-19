import { describe, expect, it } from "vitest";
import { serverHost, serverSite } from "../mcpServers";

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
