import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveActiveProjectId, setActiveProjectId } from "../projects";

const key = "duct_active_project_id";
const projects = [{ id: "a" }, { id: "b" }];

function storage() {
  const values = new Map();
  return {
    getItem: (name) => values.has(name) ? values.get(name) : null,
    setItem: (name, value) => values.set(name, String(value)),
    removeItem: (name) => values.delete(name),
  };
}

function tab(localStorage, sessionStorage = storage()) {
  return { localStorage, sessionStorage, dispatchEvent: vi.fn() };
}

afterEach(() => { delete globalThis.window; });

describe("active project per tab", () => {
  it("seeds new tabs from the last choice but keeps existing tabs independent", () => {
    const shared = storage();
    const first = tab(shared);
    globalThis.window = first;
    expect(resolveActiveProjectId(projects)).toBe("a");

    const second = tab(shared);
    globalThis.window = second;
    expect(resolveActiveProjectId(projects)).toBe("a");
    setActiveProjectId("b");
    expect(shared.getItem(key)).toBe("b");

    globalThis.window = first;
    expect(resolveActiveProjectId(projects)).toBe("a");
    globalThis.window = tab(shared);
    expect(resolveActiveProjectId(projects)).toBe("b");
    globalThis.window = tab(shared, second.sessionStorage);
    expect(resolveActiveProjectId(projects)).toBe("b");
  });

  it("repairs a deleted selection silently and leaves an empty project list alone", () => {
    const shared = storage();
    shared.setItem(key, "b");
    const current = tab(shared);
    globalThis.window = current;
    expect(resolveActiveProjectId([])).toBe("");
    expect(resolveActiveProjectId(projects)).toBe("b");
    expect(resolveActiveProjectId([{ id: "a" }])).toBe("a");
    expect(current.dispatchEvent).not.toHaveBeenCalled();
  });

  it("waits for the project list before seeding a new tab", () => {
    const shared = storage();
    globalThis.window = tab(shared);
    expect(resolveActiveProjectId([])).toBe("");
    shared.setItem(key, "b");
    expect(resolveActiveProjectId(projects)).toBe("b");
  });

  it("keeps a tab selection when session storage is blocked", () => {
    const shared = storage();
    const blocked = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
    const first = tab(shared, blocked);
    globalThis.window = first;
    expect(resolveActiveProjectId(projects)).toBe("a");
    globalThis.window = tab(shared);
    setActiveProjectId("b");
    globalThis.window = first;
    expect(resolveActiveProjectId(projects)).toBe("a");
  });
});
