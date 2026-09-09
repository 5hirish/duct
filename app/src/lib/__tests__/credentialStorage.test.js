import { describe, expect, it } from "vitest";

import { STORAGE_CLOUD, STORAGE_LOCAL, rowStorage, serverStorage } from "../credentialStorage.js";

// The one bug this module exists to prevent: a sidecar pointed at a
// deployment's Postgres answers every request, so `isLocalBackendActive()`
// says "a sidecar is serving" even when nothing is stored on this machine.
// `rowStorage` has to prefer what the row itself says over that inference —
// the inference is only the fallback for a backend too old to report it.

describe("serverStorage", () => {
  it("is cloud unless a local sidecar answered", () => {
    expect(serverStorage()).toBe(STORAGE_CLOUD);
    expect(serverStorage({ localSidecar: false })).toBe(STORAGE_CLOUD);
    expect(serverStorage({ localSidecar: true })).toBe(STORAGE_LOCAL);
  });
});

describe("rowStorage", () => {
  it("trusts the row's own storage field over the local inference", () => {
    // A sidecar IS answering (localSidecar: true), but the row says cloud — it
    // lives in staging Postgres, not on this device. The inference must lose.
    expect(rowStorage({ storage: STORAGE_CLOUD }, { localSidecar: true })).toBe(STORAGE_CLOUD);
  });

  it("falls back to inference for a row with no storage field", () => {
    // A backend too old to report `storage` — the best available guess stands.
    expect(rowStorage({}, { localSidecar: true })).toBe(STORAGE_LOCAL);
    expect(rowStorage({}, { localSidecar: false })).toBe(STORAGE_CLOUD);
  });

  it("ignores an unrecognised storage value and falls back to inference", () => {
    expect(rowStorage({ storage: "nonsense" }, { localSidecar: true })).toBe(STORAGE_LOCAL);
  });

  it("handles a missing row the same as one with no storage field", () => {
    expect(rowStorage(null, { localSidecar: false })).toBe(STORAGE_CLOUD);
    expect(rowStorage(undefined, {})).toBe(STORAGE_CLOUD);
  });
});
