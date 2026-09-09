import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONSENT_GRANTED, consentRequired, readConsentChoice, storeConsentChoice } from "../consent.js";

// This file is the one place that decides whether measurement waits on a
// decision. Every failure path here — network down, geo lookup unparseable,
// storage denied — has to resolve *toward* asking, never toward skipping the
// question: guessing wrong in that direction is the compliance violation, not
// a missed pageview.

function fakeSessionStorage() {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
}

function fakeWindow({ hostname = "app.getduct.ai", protocol = "https:", sessionStorage } = {}) {
  return {
    location: { hostname, protocol },
    sessionStorage: sessionStorage || fakeSessionStorage(),
  };
}

function fakeDocument() {
  let raw = "";
  const writes = [];
  return {
    get cookie() {
      return raw;
    },
    set cookie(value) {
      writes.push(value);
      // A real browser keeps only "name=value" from the leading segment of an
      // assignment and drops the attributes on read-back. readConsentChoice's
      // regex only ever needs that segment, so one raw slot is enough here.
      raw = value.split(";")[0].trim();
    },
    writes,
  };
}

describe("readConsentChoice / storeConsentChoice", () => {
  let doc;

  beforeEach(() => {
    doc = fakeDocument();
    globalThis.window = fakeWindow();
    globalThis.document = doc;
  });

  afterEach(() => {
    delete globalThis.window;
    delete globalThis.document;
  });

  it("round-trips a choice through the cookie", () => {
    expect(readConsentChoice()).toBeNull();
    storeConsentChoice(CONSENT_GRANTED);
    expect(readConsentChoice()).toBe(CONSENT_GRANTED);
  });

  it("scopes the cookie to the registrable domain, not the exact host", () => {
    // One journey across getduct.ai and app.getduct.ai needs one answer.
    storeConsentChoice(CONSENT_GRANTED);
    expect(doc.writes[0]).toMatch(/domain=\.getduct\.ai/);
  });

  it("marks the cookie Secure on https and omits it on http", () => {
    storeConsentChoice(CONSENT_GRANTED);
    expect(doc.writes[0]).toMatch(/; Secure/);

    globalThis.window = fakeWindow({ protocol: "http:" });
    storeConsentChoice(CONSENT_GRANTED);
    expect(doc.writes[1]).not.toMatch(/; Secure/);
  });
});

describe("consentRequired", () => {
  let fetchMock;

  beforeEach(() => {
    globalThis.window = fakeWindow();
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    delete globalThis.window;
    delete globalThis.fetch;
  });

  const traceResponse = (loc, over = {}) => ({
    ok: true,
    text: async () => `fl=1\nloc=${loc}\ncolo=MAD`,
    ...over,
  });

  it("asks in the EEA/UK/CH, and does not ask the network again once cached", async () => {
    fetchMock.mockResolvedValueOnce(traceResponse("ES"));
    expect(await consentRequired()).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    expect(await consentRequired()).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1); // served from the sessionStorage cache
  });

  it("does not ask outside the covered regions", async () => {
    fetchMock.mockResolvedValueOnce(traceResponse("US"));
    expect(await consentRequired()).toBe(false);
  });

  it("fails open — a non-OK trace response asks anyway", async () => {
    fetchMock.mockResolvedValueOnce(traceResponse("US", { ok: false }));
    expect(await consentRequired()).toBe(true);
  });

  it("fails open — a body with no loc= line asks anyway", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, text: async () => "colo=MAD" });
    expect(await consentRequired()).toBe(true);
  });

  it("fails open — a network error asks anyway", async () => {
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    expect(await consentRequired()).toBe(true);
  });

  it("fails open when sessionStorage itself is denied (Safari private mode)", async () => {
    globalThis.window = fakeWindow({
      sessionStorage: {
        getItem: () => {
          throw new Error("denied");
        },
        setItem: () => {
          throw new Error("denied");
        },
      },
    });
    fetchMock.mockResolvedValueOnce(traceResponse("US"));
    // The lookup still runs — denial only means the answer can't be cached —
    // and the write failure on the way out must not surface as an uncaught throw.
    expect(await consentRequired()).toBe(false);
  });
});
