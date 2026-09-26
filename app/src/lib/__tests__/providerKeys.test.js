import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The desktop keychain, as providerKeys.js reaches it through the shell. What
// must hold: a refusal is reported rather than read as "no key", and is never
// remembered, so asking again can succeed; a key is read from the keychain
// once, because each read can be a macOS password prompt; and pasting a key
// again repairs an item this build cannot overwrite, since that is the fix the
// key card offers.

vi.mock("../chatgpt.js", () => ({ chatgptCredential: async () => null }));

let items;
let refused;
let invoke;

// A fresh module per test: the keys it has read live at module level.
async function load() {
  vi.resetModules();
  return import("../providerKeys.js");
}

function reads(provider) {
  return invoke.mock.calls.filter(([cmd, args]) => cmd === "get_provider_key" && args.provider === provider);
}

beforeEach(() => {
  items = new Map();
  refused = new Set();
  invoke = vi.fn(async (cmd, { provider, key }) => {
    // The shell's commands reject with a plain string.
    if (refused.has(`${cmd}:${provider}`)) throw `${cmd} refused`;
    if (cmd === "get_provider_key") return items.get(provider) || "";
    if (cmd === "set_provider_key") items.set(provider, key);
    if (cmd === "delete_provider_key") {
      // A new item belongs to the build that writes it, so the ACL that
      // refused this one goes with it.
      items.delete(provider);
      refused.delete(`get_provider_key:${provider}`);
      refused.delete(`set_provider_key:${provider}`);
    }
    return null;
  });
  globalThis.window = { __TAURI__: { core: { invoke } } };
});

afterEach(() => {
  delete globalThis.window;
});

describe("desktop provider keys", () => {
  it("reports a refused read instead of an absent key, and asks again next time", async () => {
    items.set("anthropic", "sk-ant-api-test");
    refused.add("get_provider_key:anthropic");
    const { getProviderKey, readProviderKey } = await load();

    expect(await readProviderKey("anthropic")).toEqual({ key: "", error: "get_provider_key refused" });
    expect(await getProviderKey("anthropic")).toBe("");

    refused.clear();
    expect(await readProviderKey("anthropic")).toEqual({ key: "sk-ant-api-test" });
  });

  it("reads a key from the keychain once, and checks an absent one every time", async () => {
    items.set("gemini", "AIza-test");
    const { getProviderKey } = await load();

    await getProviderKey("gemini");
    expect(await getProviderKey("gemini")).toBe("AIza-test");
    expect(reads("gemini")).toHaveLength(1);

    await getProviderKey("xai");
    await getProviderKey("xai");
    expect(reads("xai")).toHaveLength(2);
  });

  it("forgets what it read when the key is removed", async () => {
    items.set("gemini", "AIza-test");
    const { clearProviderKey, getProviderKey } = await load();

    await getProviderKey("gemini");
    await clearProviderKey("gemini");
    expect(await getProviderKey("gemini")).toBe("");
  });

  it("replaces an item this build can neither read nor overwrite", async () => {
    items.set("anthropic", "sk-ant-old");
    refused.add("get_provider_key:anthropic");
    refused.add("set_provider_key:anthropic");
    const { getProviderKey, setProviderKey } = await load();

    await setProviderKey("anthropic", "sk-ant-new");
    expect(items.get("anthropic")).toBe("sk-ant-new");
    expect(await getProviderKey("anthropic")).toBe("sk-ant-new");
  });

  it("reports the original failure when the replacement fails too", async () => {
    refused.add("set_provider_key:anthropic");
    refused.add("delete_provider_key:anthropic");
    const { setProviderKey } = await load();

    await expect(setProviderKey("anthropic", "sk-ant-new")).rejects.toBe("set_provider_key refused");
  });
});
