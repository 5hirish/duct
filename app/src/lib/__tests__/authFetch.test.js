import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `authFetch.js` also imports `authToken` FROM `./api.js`'s own dependency
// graph (api.js imports authToken back from here) — the mock breaks that
// circle for this file and gives each test control over BASE and the shared
// API key without needing a real backend URL or NEXT_PUBLIC_DUCT_API_KEY.
vi.mock("../api.js", () => ({
  BASE: "http://test.local",
  backendApiKey: vi.fn(() => ""),
  // Which backend BASE points at. A function, not a constant, because the
  // whole point of the pinning tests is that it changes between page loads.
  backendIdentity: vi.fn(() => "https://api.test.local"),
}));

import { backendApiKey, backendIdentity } from "../api.js";
import {
  AUTH_BACKEND_KEY,
  AUTH_TOKEN_KEY,
  DESKTOP_AUTH_BACKEND_KEY,
  DESKTOP_AUTH_TOKEN_KEY,
  POST_SIGNIN_REDIRECT_KEY,
  SESSION_EXPIRED_EVENT,
  SIGNIN_REASON_EXPIRED,
  SIGNIN_REASON_KEY,
  SessionExpiredError,
  authToken,
  authTokenKey,
  authedHeaders,
  authedRequest,
  clearAuthToken,
  decodeJwtPayload,
  endSessionIfUnauthorized,
  hasAuthToken,
  isSessionExpired,
  isTokenValid,
  reconcileStoredSession,
  setAuthToken,
  throwForStatus,
} from "../authFetch.js";

// This file is the one place a 401 gets a meaning. Most of what is tested
// here is that meaning holding across the cases that matter in practice: the
// desktop shell keeping a separate session from the browser tab loading the
// same origin, one dead session ending exactly once, and the connector-save
// caller that must NOT be signed out from under its own callback.

function fakeJwt(payload) {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64");
  return `header.${body}.signature`;
}

function fakeWindow({ tauri } = {}) {
  const local = new Map();
  const session = new Map();
  const win = {
    localStorage: {
      getItem: (k) => (local.has(k) ? local.get(k) : null),
      setItem: (k, v) => local.set(k, String(v)),
      removeItem: (k) => local.delete(k),
    },
    sessionStorage: {
      getItem: (k) => (session.has(k) ? session.get(k) : null),
      setItem: (k, v) => session.set(k, String(v)),
      removeItem: (k) => session.delete(k),
    },
    dispatchEvent: vi.fn(),
    location: { pathname: "/connections", search: "?tab=ads" },
  };
  if (tauri) win.__TAURI__ = tauri;
  return win;
}

afterEach(() => {
  delete globalThis.window;
});

describe("decodeJwtPayload / isTokenValid", () => {
  it("decodes the claims a real token carries", () => {
    const token = fakeJwt({ sub: "ana@acme.com", name: "Ana", uid: "u1", exp: 9999999999 });
    expect(decodeJwtPayload(token)).toEqual({ sub: "ana@acme.com", name: "Ana", uid: "u1", exp: 9999999999 });
  });

  it("returns null for anything that doesn't parse, rather than throwing", () => {
    expect(decodeJwtPayload("not-a-jwt-at-all")).toBeNull();
    expect(decodeJwtPayload("header.not-valid-base64!!!.signature")).toBeNull();
    expect(decodeJwtPayload("")).toBeNull();
  });

  it("is invalid with no token, an unparseable one, or one with no exp claim", () => {
    expect(isTokenValid("")).toBe(false);
    expect(isTokenValid(null)).toBe(false);
    expect(isTokenValid("garbage")).toBe(false);
    expect(isTokenValid(fakeJwt({ sub: "ana@acme.com" }))).toBe(false);
  });

  it("is valid only while exp is still in the future", () => {
    const now = Math.floor(Date.now() / 1000);
    expect(isTokenValid(fakeJwt({ exp: now + 3600 }))).toBe(true);
    expect(isTokenValid(fakeJwt({ exp: now - 60 }))).toBe(false);
  });
});

describe("authTokenKey / storage", () => {
  beforeEach(() => {
    globalThis.window = fakeWindow();
  });

  it("the browser and the desktop shell keep separate keys", () => {
    expect(authTokenKey()).toBe(AUTH_TOKEN_KEY);
    globalThis.window = fakeWindow({ tauri: {} });
    expect(authTokenKey()).toBe(DESKTOP_AUTH_TOKEN_KEY);
  });

  it("round-trips a token under whichever key this shell owns", () => {
    expect(hasAuthToken()).toBe(false);
    setAuthToken("t1");
    expect(authToken()).toBe("t1");
    expect(hasAuthToken()).toBe(true);
    expect(globalThis.window.localStorage.getItem(AUTH_TOKEN_KEY)).toBe("t1");

    clearAuthToken();
    expect(hasAuthToken()).toBe(false);
  });

  it("a desktop session and a browser session on the same origin do not collide", () => {
    globalThis.window = fakeWindow({ tauri: {} });
    setAuthToken("desktop-token");
    expect(globalThis.window.localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    expect(globalThis.window.localStorage.getItem(DESKTOP_AUTH_TOKEN_KEY)).toBe("desktop-token");
  });
});

// A session token is signed by whichever backend minted it, and the desktop
// shell can address two: its bundled sidecar and the hosted API. The token from
// the wrong one is well-formed, unexpired and correctly signed — so it used to
// arrive as a 401 and take the whole session down with it. These pin the
// difference between "your session ended" and "that token is not for this
// server".
describe("reconcileStoredSession", () => {
  beforeEach(() => {
    globalThis.window = fakeWindow();
    backendIdentity.mockReturnValue("https://api.test.local");
  });

  it("records the minting backend beside the token", () => {
    setAuthToken("t1");
    expect(globalThis.window.localStorage.getItem(AUTH_BACKEND_KEY)).toBe("https://api.test.local");
  });

  it("keeps a session minted by the backend this page load talks to", () => {
    setAuthToken("t1");
    expect(reconcileStoredSession()).toBe("match");
    expect(authToken()).toBe("t1");
  });

  it("discards a session minted by the other backend", () => {
    setAuthToken("t1");
    backendIdentity.mockReturnValue("local");
    expect(reconcileStoredSession()).toBe("discarded");
    expect(hasAuthToken()).toBe(false);
  });

  it("discarding is quiet — it is not the treatment a dead session gets", () => {
    setAuthToken("t1");
    backendIdentity.mockReturnValue("local");
    reconcileStoredSession();
    // No SESSION_EXPIRED_EVENT, no parked redirect, no "your session ended"
    // notice. The app renders signed out, which is true of this backend.
    expect(globalThis.window.dispatchEvent).not.toHaveBeenCalled();
    expect(globalThis.window.sessionStorage.getItem(POST_SIGNIN_REDIRECT_KEY)).toBeNull();
    expect(globalThis.window.sessionStorage.getItem(SIGNIN_REASON_KEY)).toBeNull();
  });

  it("leaves a session stored before issuers were recorded alone", () => {
    // Signing everyone out once on upgrade is the exact thing this prevents.
    globalThis.window.localStorage.setItem(AUTH_TOKEN_KEY, "legacy-token");
    expect(reconcileStoredSession()).toBe("unpinned");
    expect(authToken()).toBe("legacy-token");
  });

  it("an unknown base is not a mismatch", () => {
    setAuthToken("t1");
    backendIdentity.mockReturnValue("");
    expect(reconcileStoredSession()).toBe("match");
    expect(authToken()).toBe("t1");
  });

  it("clearing a session takes its issuer with it", () => {
    setAuthToken("t1");
    clearAuthToken();
    expect(globalThis.window.localStorage.getItem(AUTH_BACKEND_KEY)).toBeNull();
  });

  it("the shell judges its own session, not the browser tab's", () => {
    globalThis.window = fakeWindow({ tauri: {} });
    setAuthToken("desktop-token");
    expect(globalThis.window.localStorage.getItem(AUTH_BACKEND_KEY)).toBeNull();
    expect(globalThis.window.localStorage.getItem(DESKTOP_AUTH_BACKEND_KEY)).toBe(
      "https://api.test.local"
    );

    backendIdentity.mockReturnValue("local");
    expect(reconcileStoredSession()).toBe("discarded");
    expect(globalThis.window.localStorage.getItem(DESKTOP_AUTH_TOKEN_KEY)).toBeNull();
  });
});

describe("authedHeaders", () => {
  beforeEach(() => {
    globalThis.window = fakeWindow();
  });

  it("carries the service key and, once signed in, the bearer token", () => {
    backendApiKey.mockReturnValue("service-key");
    expect(authedHeaders()).toEqual({ "X-API-Key": "service-key" });

    setAuthToken("user-token");
    expect(authedHeaders()).toEqual({ "X-API-Key": "service-key", Authorization: "Bearer user-token" });
  });

  it("omits the API key header entirely when none is configured", () => {
    backendApiKey.mockReturnValue("");
    expect(authedHeaders()).toEqual({});
  });

  it("extra headers pass through untouched", () => {
    backendApiKey.mockReturnValue("");
    expect(authedHeaders({ "Content-Type": "application/json" })).toEqual({ "Content-Type": "application/json" });
  });
});

describe("throwForStatus / endSessionIfUnauthorized", () => {
  const jsonRes = (status, body) => ({ status, json: async () => body });

  beforeEach(() => {
    globalThis.window = fakeWindow();
    backendApiKey.mockReturnValue("");
    // Re-arms the once-only session-ended guard (see setAuthToken's comment)
    // so a previous test's retirement can never leak into this one.
    setAuthToken("seed-token");
  });

  it("a 401 clears the token, parks the redirect, and fires the event exactly once", async () => {
    await expect(throwForStatus(jsonRes(401, { detail: "User not found" }))).rejects.toBeInstanceOf(
      SessionExpiredError,
    );

    expect(hasAuthToken()).toBe(false);
    expect(window.sessionStorage.getItem(POST_SIGNIN_REDIRECT_KEY)).toBe("/connections?tab=ads");
    expect(window.sessionStorage.getItem(SIGNIN_REASON_KEY)).toBe(SIGNIN_REASON_EXPIRED);
    expect(window.dispatchEvent).toHaveBeenCalledTimes(1);
    expect(window.dispatchEvent.mock.calls[0][0].type).toBe(SESSION_EXPIRED_EVENT);

    // A second 401 while already signed out must not re-park or re-fire —
    // that is the "four panels, one 401 each" case this guard exists for.
    await expect(throwForStatus(jsonRes(401, {}))).rejects.toBeInstanceOf(SessionExpiredError);
    expect(window.dispatchEvent).toHaveBeenCalledTimes(1);
  });

  it("the thrown error carries the backend's detail and status", async () => {
    await expect(throwForStatus(jsonRes(401, { detail: "User not found" }))).rejects.toMatchObject({
      message: "User not found",
      status: 401,
      sessionExpired: true,
    });
  });

  it("isSessionExpired is true only for that error, not any thrown error", () => {
    expect(isSessionExpired(new SessionExpiredError("x", 401))).toBe(true);
    expect(isSessionExpired(new Error("boom"))).toBe(false);
    expect(isSessionExpired(null)).toBe(false);
  });

  it("retireSession: false leaves the session alone — the connector-save path", async () => {
    await expect(
      throwForStatus(jsonRes(401, { detail: "User not found" }), { retireSession: false }),
    ).rejects.not.toBeInstanceOf(SessionExpiredError);

    expect(hasAuthToken()).toBe(true);
    expect(window.dispatchEvent).not.toHaveBeenCalled();
  });

  it("a non-401 is a plain error carrying the status; the session is untouched", async () => {
    await expect(throwForStatus(jsonRes(500, { detail: "boom" }))).rejects.toMatchObject({
      message: "boom",
      status: 500,
    });
    expect(hasAuthToken()).toBe(true);
    expect(window.dispatchEvent).not.toHaveBeenCalled();
  });

  it("falls back to a status-shaped message when the error body isn't JSON", async () => {
    const res = {
      status: 502,
      json: async () => {
        throw new Error("not json");
      },
    };
    await expect(throwForStatus(res)).rejects.toMatchObject({ message: "Server error 502" });
  });

  it("endSessionIfUnauthorized is false for anything but 401, without touching the session", () => {
    expect(endSessionIfUnauthorized(jsonRes(403, {}))).toBe(false);
    expect(window.dispatchEvent).not.toHaveBeenCalled();
    expect(hasAuthToken()).toBe(true);

    expect(endSessionIfUnauthorized(jsonRes(401, {}))).toBe(true);
    expect(window.dispatchEvent).toHaveBeenCalledTimes(1);
  });
});

describe("authedFetch / authedRequest", () => {
  let fetchMock;

  beforeEach(() => {
    globalThis.window = fakeWindow();
    backendApiKey.mockReturnValue("service-key");
    // "" reads back as no token and, via setAuthToken, re-arms the session
    // guard — so this describe block can't inherit state from the last one.
    setAuthToken("");
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    delete globalThis.fetch;
  });

  it("sends the service key and bearer token against BASE", async () => {
    setAuthToken("user-token");
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: true }) });

    await authedRequest("/api/projects");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://test.local/api/projects");
    expect(init.headers["X-API-Key"]).toBe("service-key");
    expect(init.headers.Authorization).toBe("Bearer user-token");
  });

  it("JSON-encodes a body and sets Content-Type only when one is given", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) });
    await authedRequest("/api/projects", { method: "POST", body: { name: "Acme" } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).toBe(JSON.stringify({ name: "Acme" }));
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("a GET with no body sends neither Content-Type nor a body", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) });
    await authedRequest("/api/projects");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).toBeUndefined();
    expect(init.headers["Content-Type"]).toBeUndefined();
  });

  it("a 204 resolves to null rather than parsing an empty body", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error("no body to parse");
      },
    });
    await expect(authedRequest("/api/projects/1")).resolves.toBeNull();
  });

  it("a 401 from a real call retires the session end to end", async () => {
    setAuthToken("user-token");
    fetchMock.mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({ detail: "User not found" }) });

    await expect(authedRequest("/api/projects")).rejects.toBeInstanceOf(SessionExpiredError);
    expect(hasAuthToken()).toBe(false);
  });
});
