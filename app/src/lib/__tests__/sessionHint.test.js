import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api.js", () => ({
  BASE: "http://test.local",
  backendApiKey: vi.fn(() => ""),
  backendIdentity: vi.fn(() => "https://api.test.local"),
}));

import { AUTH_TOKEN_KEY, DESKTOP_AUTH_TOKEN_KEY } from "../authFetch.js";
import { SESSION_HINT_SCRIPT, clearSessionHint } from "../sessionHint.js";

// The hint runs before any module loads, so it cannot import the keys or the
// guest check; it restates them. These tests are what keeps the copy honest.

const toBase64Url = (value) =>
  Buffer.from(JSON.stringify(value)).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const jwt = (claims) => `header.${toBase64Url(claims)}.signature`;
const inAnHour = () => Math.floor(Date.now() / 1000) + 3600;

/** Run the inline script against a fake document; returns what it set. */
function runHint({ stored = {}, tauri = false } = {}) {
  const dataset = {};
  const window = tauri ? { __TAURI__: {} } : {};
  const localStorage = { getItem: (key) => stored[key] ?? null };
  const document = { documentElement: { dataset } };
  new Function("window", "localStorage", "document", "atob", SESSION_HINT_SCRIPT)(
    window,
    localStorage,
    document,
    (b64) => Buffer.from(b64, "base64").toString("binary"),
  );
  return dataset.session;
}

describe("SESSION_HINT_SCRIPT", () => {
  it("marks a member's session before paint", () => {
    expect(runHint({ stored: { [AUTH_TOKEN_KEY]: jwt({ exp: inAnHour() }) } })).toBe("member");
  });

  it("reads the shell's own key in the desktop app", () => {
    const token = jwt({ exp: inAnHour() });
    expect(runHint({ tauri: true, stored: { [DESKTOP_AUTH_TOKEN_KEY]: token } })).toBe("member");
    expect(runHint({ tauri: true, stored: { [AUTH_TOKEN_KEY]: token } })).toBeUndefined();
  });

  it("leaves a guest on the front door, which is where they become a member", () => {
    const token = jwt({ exp: inAnHour(), guest: true });
    expect(runHint({ stored: { [AUTH_TOKEN_KEY]: token } })).toBeUndefined();
  });

  it("ignores an expired session and anything unreadable", () => {
    expect(runHint({ stored: { [AUTH_TOKEN_KEY]: jwt({ exp: 1 }) } })).toBeUndefined();
    expect(runHint({ stored: { [AUTH_TOKEN_KEY]: "not-a-jwt" } })).toBeUndefined();
    expect(runHint()).toBeUndefined();
  });
});

describe("clearSessionHint", () => {
  afterEach(() => {
    delete globalThis.document;
  });

  it("takes the hint off so a signed-out visitor sees the front door", () => {
    globalThis.document = { documentElement: { dataset: { session: "member" } } };
    clearSessionHint();
    expect(globalThis.document.documentElement.dataset.session).toBeUndefined();
  });
});
