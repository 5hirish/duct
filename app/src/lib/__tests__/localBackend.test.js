import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// What `LocalBackendGate` relies on to render the server's HTML and hydrate it
// safely: a browser settles synchronously, the server answers without
// recording anything, and a shell waits — with the stored session reconciled
// exactly once, before anything below the gate can read it.

vi.mock("../api.js", () => ({ useLocalBackend: vi.fn() }));
vi.mock("../authFetch.js", () => ({ reconcileStoredSession: vi.fn() }));

let localBackend;
let reconcileStoredSession;

beforeEach(async () => {
  vi.resetModules();
  ({ reconcileStoredSession } = await import("../authFetch.js"));
  reconcileStoredSession.mockClear();
  localBackend = await import("../localBackend.js");
});

afterEach(() => {
  delete globalThis.window;
});

describe("settledBackend", () => {
  it("answers hosted on the server without settling, since every request shares the module", () => {
    expect(localBackend.settledBackend()).toEqual({ active: false });
    expect(reconcileStoredSession).not.toHaveBeenCalled();
    globalThis.window = {};
    // Still unsettled: the first real answer is the browser's.
    localBackend.settledBackend();
    expect(reconcileStoredSession).toHaveBeenCalledTimes(1);
  });

  it("settles a browser on the first call and reconciles the session once", () => {
    globalThis.window = {};
    expect(localBackend.settledBackend()).toEqual({ active: false });
    localBackend.settledBackend();
    expect(reconcileStoredSession).toHaveBeenCalledTimes(1);
    expect(localBackend.isLocalBackendActive()).toBe(false);
  });

  it("makes a desktop shell wait for its answer", async () => {
    globalThis.window = {
      __TAURI__: { core: { invoke: vi.fn(async () => ({ version: "0.7.2", capabilities: {} })) } },
    };
    expect(localBackend.settledBackend()).toBeNull();
    expect(reconcileStoredSession).not.toHaveBeenCalled();
    await expect(localBackend.initLocalBackend()).resolves.toEqual({ active: false });
    expect(localBackend.settledBackend()).toEqual({ active: false });
    expect(reconcileStoredSession).toHaveBeenCalledTimes(1);
  });

  it("does not judge the session against a sidecar that failed to start", async () => {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: vi.fn(async (command) => {
            if (command === "get_shell_info") return { capabilities: { localSidecar: true } };
            throw new Error("sidecar binary missing");
          }),
        },
      },
    };
    const result = await localBackend.initLocalBackend();
    expect(result.error).toMatch(/sidecar binary missing/);
    expect(reconcileStoredSession).not.toHaveBeenCalled();
  });
});
