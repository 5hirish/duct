import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { clearDraft, readDraft, writeDraft } from "../composerDraft";

function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    size: () => m.size,
  };
}

// Node may or may not define a Web Storage global of its own (behind a flag
// in 22, on by default later), so the test installs and removes the binding
// explicitly instead of assigning over whatever is there. sessionStorage, not
// localStorage: a draft is per tab, so it cannot follow a shared browser's
// next sign-in.
function setStorage(value) {
  Object.defineProperty(globalThis, "sessionStorage", { value, configurable: true, writable: true });
}

describe("composer drafts", () => {
  let storage;
  beforeEach(() => {
    storage = fakeStorage();
    setStorage(storage);
  });
  afterEach(() => {
    setStorage(undefined);
  });

  it("round-trips per key and clears on send", () => {
    writeDraft("insights:p1:c1", "why did CPA");
    expect(readDraft("insights:p1:c1")).toBe("why did CPA");
    expect(readDraft("insights:p1:c2")).toBe("");
    clearDraft("insights:p1:c1");
    expect(readDraft("insights:p1:c1")).toBe("");
  });

  it("an emptied box removes the entry instead of storing an empty string", () => {
    writeDraft("k", "a");
    writeDraft("k", "");
    expect(storage.size()).toBe(0);
  });

  it("no key, nothing kept — the preview gallery and a shell with no thread", () => {
    writeDraft("", "lost on purpose");
    expect(storage.size()).toBe(0);
    expect(readDraft("")).toBe("");
  });

  it("a throwing storage is a quiet loss, never an exception", () => {
    const boom = () => {
      throw new Error("QuotaExceededError");
    };
    setStorage({ getItem: boom, setItem: boom, removeItem: boom });
    expect(() => writeDraft("k", "x")).not.toThrow();
    expect(() => clearDraft("k")).not.toThrow();
    expect(readDraft("k")).toBe("");
  });

  it("never touches localStorage, where a draft would outlive the tab and the sign-in", () => {
    const touched = () => {
      throw new Error("localStorage must not be used for drafts");
    };
    Object.defineProperty(globalThis, "localStorage", {
      value: { getItem: touched, setItem: touched, removeItem: touched },
      configurable: true,
      writable: true,
    });
    writeDraft("k", "x");
    expect(readDraft("k")).toBe("x");
    Object.defineProperty(globalThis, "localStorage", { value: undefined, configurable: true, writable: true });
  });

  it("no storage at all (a server render) is the same quiet loss", () => {
    setStorage(undefined);
    expect(readDraft("k")).toBe("");
    expect(() => writeDraft("k", "x")).not.toThrow();
    expect(() => clearDraft("k")).not.toThrow();
  });
});
