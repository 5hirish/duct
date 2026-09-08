import { describe, expect, it, vi } from "vitest";

import { fetchDeployedBuild, isStale } from "../appVersion.js";

// The whole failure surface of this feature is false positives. A notice that
// asks someone to reload for no reason is worse than no notice at all, because
// it is the thing that teaches them to ignore the one that matters — so most of
// these tests are about staying quiet.

describe("isStale", () => {
  it("is true only when both builds are known and they differ", () => {
    expect(isStale("b2", "b1")).toBe(true);
  });

  it("is quiet when the deployed build could not be determined", () => {
    // An offline poll, a cold start, a 500. "We could not tell" must never
    // read as "it changed".
    expect(isStale("", "b1")).toBe(false);
  });

  it("is quiet when this build has no id of its own", () => {
    // `next dev` bakes nothing, so every comparison would be "" !== something
    // and the notice would be permanent on the first check.
    expect(isStale("b2", "")).toBe(false);
  });

  it("is quiet when the builds match", () => {
    expect(isStale("b1", "b1")).toBe(false);
  });
});

describe("fetchDeployedBuild", () => {
  const res = (over = {}) => ({
    ok: true,
    headers: { get: () => null },
    json: async () => ({}),
    ...over,
  });

  it("prefers the header, so an unparseable body still answers", async () => {
    const fake = vi.fn(async () => res({ headers: { get: (n) => (n === "x-duct-build" ? "abc" : null) } }));
    await expect(fetchDeployedBuild(fake)).resolves.toBe("abc");
  });

  it("falls back to the body when a proxy stripped the header", async () => {
    const fake = vi.fn(async () => res({ json: async () => ({ build: "xyz" }) }));
    await expect(fetchDeployedBuild(fake)).resolves.toBe("xyz");
  });

  it("asks for no caching — a cached 200 makes the check silently useless", async () => {
    const fake = vi.fn(async () => res());
    await fetchDeployedBuild(fake);
    const [, init] = fake.mock.calls[0];
    expect(init.cache).toBe("no-store");
    expect(init.headers["cache-control"]).toBe("no-cache");
  });

  it("returns empty rather than throwing when the network fails", async () => {
    const fake = vi.fn(async () => {
      throw new Error("offline");
    });
    await expect(fetchDeployedBuild(fake)).resolves.toBe("");
  });

  it("returns empty on a non-ok response", async () => {
    const fake = vi.fn(async () => res({ ok: false }));
    await expect(fetchDeployedBuild(fake)).resolves.toBe("");
  });

  it("returns empty when the body carries no build", async () => {
    const fake = vi.fn(async () => res({ json: async () => ({ nope: 1 }) }));
    await expect(fetchDeployedBuild(fake)).resolves.toBe("");
  });
});
