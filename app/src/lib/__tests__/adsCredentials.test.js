import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  getAdsLoginCustomerId,
  googleAdsRequestFields,
  setAdsLoginCustomerId,
} from "../adsCredentials.js";

// The developer token this module used to hold is gone (Google sunset those on
// 2026-09-09). What is left is the MCC id, and the thing worth pinning is its
// normalisation: Google Ads shows manager account ids dashed and the API
// rejects them that way, so a token pasted straight from the UI has to lose its
// dashes on the way in, not at some later call site.

function fakeWindow() {
  const session = new Map();
  return {
    sessionStorage: {
      getItem: (k) => (session.has(k) ? session.get(k) : null),
      setItem: (k, v) => session.set(k, String(v)),
      removeItem: (k) => session.delete(k),
    },
  };
}

beforeEach(() => {
  globalThis.window = fakeWindow();
});

afterEach(() => {
  delete globalThis.window;
});

describe("Google Ads manager account id", () => {
  it("strips dashes from the MCC login customer id", () => {
    setAdsLoginCustomerId("123-456-7890");
    expect(getAdsLoginCustomerId()).toBe("1234567890");
  });

  it("a blank login customer id clears the stored one", () => {
    setAdsLoginCustomerId("123-456-7890");
    setAdsLoginCustomerId("");
    expect(getAdsLoginCustomerId()).toBe("");
  });

  it("bundles the request fields for a body", () => {
    setAdsLoginCustomerId("123-456-7890");
    expect(googleAdsRequestFields()).toEqual({ login_customer_id: "1234567890" });
  });

  it("reads as unset when storage throws", () => {
    globalThis.window = {
      sessionStorage: {
        getItem: () => {
          throw new Error("storage disabled");
        },
        setItem: () => {
          throw new Error("storage disabled");
        },
        removeItem: () => {},
      },
    };
    expect(getAdsLoginCustomerId()).toBe("");
    expect(() => setAdsLoginCustomerId("1234567890")).not.toThrow();
  });
});
