import { beforeEach, describe, expect, it, vi } from "vitest";

// The catch-up offer lends this device's keys to memory consolidation. What it
// must never do: send a ChatGPT plan token (the backend cannot spend one here,
// and fetching it refreshes it), call while signed out, or sign the person out
// when a background call gets a 401.

const keys = {};
vi.mock("../providerKeys", () => ({
  // Every credential that rides as a header, a connected endpoint included:
  // the memory sweep can run on one as well as on a vendor key.
  KEYED_PROVIDERS: [
    { id: "anthropic", header: "X-Provider-Anthropic" },
    { id: "gemini", header: "X-Provider-Gemini" },
    { id: "compatible", header: "X-Provider-Compatible" },
  ],
  getProviderKey: vi.fn(async (id) => keys[id] || ""),
}));

const fetchCalls = [];
let token = "jwt";
vi.mock("../authFetch", () => ({
  authToken: () => token,
  authedFetch: vi.fn(async (path, opts) => {
    fetchCalls.push({ path, opts });
    return { json: async () => ({ scheduled: true }) };
  }),
}));

import { apiKeyHeaders, catchUpMemory } from "../memoryCatchUp.js";

beforeEach(() => {
  for (const k of Object.keys(keys)) delete keys[k];
  fetchCalls.length = 0;
  token = "jwt";
});

describe("memory catch-up", () => {
  it("sends only the API keys this device holds", async () => {
    keys.gemini = "AIza-test";
    expect(await apiKeyHeaders()).toEqual({ "X-Provider-Gemini": "AIza-test" });
  });

  it("lends a connected endpoint like any key", async () => {
    keys.compatible = "oaic1.endpoint";
    expect(await apiKeyHeaders()).toEqual({ "X-Provider-Compatible": "oaic1.endpoint" });
  });

  it("offers the keys without risking the session", async () => {
    keys.anthropic = "sk-ant-api-test";
    expect(await catchUpMemory()).toBe(true);
    const [{ path, opts }] = fetchCalls;
    expect(path).toBe("/api/user/memory/catch-up");
    expect(opts.headers).toEqual({ "X-Provider-Anthropic": "sk-ant-api-test" });
    expect(opts.retireSession).toBe(false);
  });

  it("does nothing with no keys to lend or nobody signed in", async () => {
    expect(await catchUpMemory()).toBe(false);
    keys.gemini = "AIza-test";
    token = "";
    expect(await catchUpMemory()).toBe(false);
    expect(fetchCalls).toEqual([]);
  });
});
