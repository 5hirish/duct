// A draft reaches the server as a draft, not as a copy of the whole project,
// so the server merges it against what it holds (backend/service/project_draft.py).
// Drafts for one project arrive in the order they were made: at equal rank
// the later one is meant to win.
//
// The suite runs without a DOM by choice (see vitest.config.js), so the store's
// storage calls are stubbed and the network module is replaced.

import { afterAll, describe, expect, it, vi } from "vitest";

const net = vi.hoisted(() => ({ calls: [], gates: new Map() }));

vi.mock("../projectsApi", () => ({
  hasAuthToken: () => true,
  fetchProjectsRemote: async () => [],
  deleteProjectRemote: async () => {},
  upsertProjectRemote: async (project) => {
    net.calls.push(["upsert", project.id]);
    return null;
  },
  postProjectDraftRemote: async (id, draft) => {
    net.calls.push(["draft", draft.layer]);
    await net.gates.get(draft.layer);
    net.calls.push(["landed", draft.layer]);
    return null;
  },
}));

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

const { applyProjectDraft, PROVENANCE_CRAWL, PROVENANCE_INFERRED } = await import("../projectDraft");
const { pushDraftToBackend } = await import("../projects");

afterAll(() => {
  delete globalThis.window;
});

describe("sending drafts", () => {
  it("sends the draft itself, never the merged project", async () => {
    net.calls.length = 0;
    const draft = { layer: "crawl", fields: { pitch: { value: "Dinners, planned.", provenance: PROVENANCE_CRAWL } } };
    const saved = applyProjectDraft(draft);
    expect(saved.company.pitch).toBe("Dinners, planned."); // merged here at once
    await pushDraftToBackend(saved.id, { layer: "probe", fields: {} });
    expect(net.calls).toEqual([["draft", "crawl"], ["landed", "crawl"], ["draft", "probe"], ["landed", "probe"]]);
  });

  it("holds a project's second draft until its first has landed", async () => {
    net.calls.length = 0;
    let release;
    net.gates.set("first", new Promise((resolve) => (release = resolve)));
    const first = pushDraftToBackend("p1", { layer: "first", fields: {} });
    const second = pushDraftToBackend("p1", {
      layer: "second",
      fields: { industry: { value: "Fintech", provenance: PROVENANCE_INFERRED } },
    });
    await Promise.resolve();
    expect(net.calls).toEqual([["draft", "first"]]);
    release();
    await Promise.all([first, second]);
    expect(net.calls).toEqual([["draft", "first"], ["landed", "first"], ["draft", "second"], ["landed", "second"]]);
  });
});
