import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  _resetDetachedRunsForTests,
  forgetDetachedRun,
  listDetachedRuns,
  rememberDetachedRun,
  runsUnder,
  subscribeDetachedRuns,
} from "../liveRuns";

function fakeStorage() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  };
}

describe("detached runs", () => {
  beforeEach(() => {
    globalThis.sessionStorage = fakeStorage();
    _resetDetachedRunsForTests();
  });
  afterEach(() => {
    delete globalThis.sessionStorage;
  });

  it("remembers a run once per session and forgets it by session id", () => {
    rememberDetachedRun({ agentType: "insights", sessionId: "s1", conversationId: "c1", handleKey: "k" });
    rememberDetachedRun({ agentType: "insights", sessionId: "s1", conversationId: "c1", handleKey: "k" });
    expect(listDetachedRuns().map((r) => r.sessionId)).toEqual(["s1"]);
    forgetDetachedRun("s1");
    expect(listDetachedRuns()).toEqual([]);
  });

  it("survives a reload of the module from the tab's storage", () => {
    rememberDetachedRun({ agentType: "audit_seo", sessionId: "s2" });
    _resetDetachedRunsForTests();
    expect(listDetachedRuns()[0]).toMatchObject({ agentType: "audit_seo", sessionId: "s2" });
  });

  it("hands readers the same array until something changes", () => {
    rememberDetachedRun({ agentType: "insights", sessionId: "s1" });
    const a = listDetachedRuns();
    forgetDetachedRun("not-there");
    expect(listDetachedRuns()).toBe(a);
    forgetDetachedRun("s1");
    expect(listDetachedRuns()).not.toBe(a);
  });

  it("tells subscribers on every change", () => {
    const seen = vi.fn();
    const off = subscribeDetachedRuns(seen);
    rememberDetachedRun({ agentType: "insights", sessionId: "s1" });
    forgetDetachedRun("s1");
    off();
    rememberDetachedRun({ agentType: "insights", sessionId: "s3" });
    expect(seen).toHaveBeenCalledTimes(2);
  });

  it("is empty and quiet when storage throws", () => {
    globalThis.sessionStorage = {
      getItem() { throw new Error("blocked"); },
      setItem() { throw new Error("blocked"); },
    };
    _resetDetachedRunsForTests();
    expect(listDetachedRuns()).toEqual([]);
    expect(() => rememberDetachedRun({ agentType: "insights", sessionId: "s1" })).not.toThrow();
    expect(listDetachedRuns().map((r) => r.sessionId)).toEqual(["s1"]);
  });

  it("lights the sidebar entry each agent's workspace lives under", () => {
    const runs = [
      { agentType: "insights", sessionId: "a" },
      { agentType: "audit_seo", sessionId: "b" },
      { agentType: "tiktok_studio", sessionId: "c" },
      { agentType: "unknown", sessionId: "d" },
    ];
    expect(runsUnder(runs, "/insights/organic-growth").map((r) => r.sessionId)).toEqual(["a"]);
    expect(runsUnder(runs, "/audit/seo").map((r) => r.sessionId)).toEqual(["b"]);
    expect(runsUnder(runs, "/content").map((r) => r.sessionId)).toEqual(["c"]);
    expect(runsUnder(runs, "/execute")).toEqual([]);
    expect(runsUnder(runs, "")).toEqual([]);
  });
});
