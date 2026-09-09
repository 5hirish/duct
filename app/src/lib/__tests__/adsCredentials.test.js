import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearAdsDeveloperToken,
  getAdsDeveloperToken,
  getAdsLoginCustomerId,
  googleAdsByoCredentials,
  setAdsDeveloperToken,
  setAdsLoginCustomerId,
} from "../adsCredentials.js";

// Storage is shell-aware: sessionStorage on the web (ephemeral — the right
// instinct for a value this sensitive), the OS keychain on desktop via Tauri
// invoke commands. The tests exist to pin which shell gets which: a web-build
// regression that started calling the keychain invoke instead would fail
// silently everywhere but inside Tauri, so it has to be asserted, not assumed.

function fakeWindow({ tauri } = {}) {
  const session = new Map();
  const win = {
    sessionStorage: {
      getItem: (k) => (session.has(k) ? session.get(k) : null),
      setItem: (k, v) => session.set(k, String(v)),
      removeItem: (k) => session.delete(k),
    },
  };
  if (tauri) win.__TAURI__ = tauri;
  return win;
}

afterEach(() => {
  delete globalThis.window;
});

describe("web build — sessionStorage", () => {
  beforeEach(() => {
    globalThis.window = fakeWindow();
  });

  it("round-trips the developer token, trimmed", async () => {
    expect(await getAdsDeveloperToken()).toBe("");
    await setAdsDeveloperToken("  abc123  ");
    expect(await getAdsDeveloperToken()).toBe("abc123");
  });

  it("clearing removes the key rather than storing an empty string", async () => {
    await setAdsDeveloperToken("abc123");
    await clearAdsDeveloperToken();
    expect(globalThis.window.sessionStorage.getItem("gads_developer_token")).toBeNull();
  });

  it("strips dashes from the MCC login customer id", () => {
    setAdsLoginCustomerId("123-456-7890");
    expect(getAdsLoginCustomerId()).toBe("1234567890");
  });

  it("a blank login customer id clears the stored one", () => {
    setAdsLoginCustomerId("123-456-7890");
    setAdsLoginCustomerId("");
    expect(getAdsLoginCustomerId()).toBe("");
  });

  it("bundles both fields for the request body", async () => {
    await setAdsDeveloperToken("abc123");
    setAdsLoginCustomerId("123-456-7890");
    expect(await googleAdsByoCredentials()).toEqual({
      developer_token: "abc123",
      login_customer_id: "1234567890",
    });
  });
});

describe("desktop shell — OS keychain", () => {
  it("reads and writes through the keychain invoke commands, not sessionStorage", async () => {
    const invoke = vi.fn(async (cmd) => (cmd === "get_provider_key" ? "keychain-token" : undefined));
    globalThis.window = fakeWindow({ tauri: { core: { invoke } } });

    expect(await getAdsDeveloperToken()).toBe("keychain-token");
    expect(invoke).toHaveBeenCalledWith("get_provider_key", { provider: "google_ads_developer_token" });

    await setAdsDeveloperToken("new-token");
    expect(invoke).toHaveBeenCalledWith("set_provider_key", {
      provider: "google_ads_developer_token",
      key: "new-token",
    });
    expect(globalThis.window.sessionStorage.getItem("gads_developer_token")).toBeNull();
  });

  it("clearing calls delete_provider_key rather than set with an empty value", async () => {
    const invoke = vi.fn(async () => undefined);
    globalThis.window = fakeWindow({ tauri: { core: { invoke } } });

    await setAdsDeveloperToken("");
    expect(invoke).toHaveBeenCalledWith("delete_provider_key", expect.anything());
    expect(invoke).not.toHaveBeenCalledWith("set_provider_key", expect.anything());
  });

  it("a keychain failure is swallowed rather than thrown", async () => {
    const invoke = vi.fn(async () => {
      throw new Error("keychain locked");
    });
    globalThis.window = fakeWindow({ tauri: { core: { invoke } } });

    await expect(getAdsDeveloperToken()).resolves.toBe("");
    await expect(setAdsDeveloperToken("x")).resolves.toBeUndefined();
  });
});
