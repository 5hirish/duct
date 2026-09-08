// Matching a project by its website — the key `/start` uses to decide whether
// an audit is updating something that exists or starting something new.
//
// The rule is host-level: case and a leading `www.` are noise, a subdomain is
// not. `blog.acme.com` and `acme.com` are two legitimate audit targets with
// different findings, and folding them together would write one site's report
// into the other site's project.
//
// The suite runs without a DOM by choice (see vitest.config.js), so the store's
// two storage calls are stubbed rather than pulling in jsdom for one file.

import { afterAll, beforeEach, describe, expect, it } from "vitest";

function fakeWindow() {
  const store = new Map();
  return {
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, String(value)),
      removeItem: (key) => store.delete(key),
    },
    dispatchEvent: () => true,
  };
}

globalThis.window = fakeWindow();

const { createProject, projectsForSite, siteKey } = await import("../projects");

beforeEach(() => {
  globalThis.window = fakeWindow();
});

afterAll(() => {
  delete globalThis.window;
});

describe("siteKey", () => {
  it("ignores scheme, case, path and www", () => {
    const key = siteKey("acme.com");
    expect(key).toBe("acme.com");
    for (const form of [
      "https://acme.com",
      "http://acme.com/pricing?utm=x",
      "https://www.acme.com/",
      "ACME.com",
      "www.ACME.com",
    ]) {
      expect(siteKey(form)).toBe(key);
    }
  });

  it("keeps a subdomain, which is a different site to audit", () => {
    expect(siteKey("blog.acme.com")).not.toBe(siteKey("acme.com"));
  });

  it("is empty for anything it cannot parse, and empty never matches", () => {
    expect(siteKey("")).toBe("");
    expect(siteKey(null)).toBe("");
    expect(siteKey("not a url at all")).toBe("");
    expect(projectsForSite("")).toEqual([]);
  });
});

describe("projectsForSite", () => {
  it("finds the project for a site however either address was written", () => {
    createProject({ name: "Acme", company: { website_url: "https://www.Acme.com/" } });
    const found = projectsForSite("acme.com");
    expect(found).toHaveLength(1);
    expect(found[0].name).toBe("Acme");
  });

  it("does not match a project that never recorded a website", () => {
    createProject({ name: "No site", company: { website_url: "" } });
    expect(projectsForSite("acme.com")).toEqual([]);
  });

  it("returns every match rather than a guess", () => {
    createProject({ name: "Acme one", company: { website_url: "acme.com" } });
    createProject({ name: "Acme two", company: { website_url: "https://acme.com" } });
    expect(projectsForSite("acme.com")).toHaveLength(2);
  });
});
