import { beforeEach, describe, expect, it } from "vitest";

// The profile moved from a dialog backed by `duct_user_preferences` to a page
// backed by a server row, and two of the dialog's controls were cut. What these
// cover is the seam that decision creates: an upgrading user must not quietly
// lose the intent they had expressed, and the fields that moved must stop
// living in two places at once.

import { PREFS_KEY, loadPreferences } from "../userPreferences.js";
import {
  NOTES_MAX_CHARS,
  PROFILE_DEFAULTS,
  PROFILE_KEY,
  detectTimezone,
  listTimezones,
  loadProfile,
  migrateLegacyPreferences,
  zoneLabel,
  zoneOffsetLabel,
  zoneRegion,
} from "../userProfile.js";

function fakeLocalStorage() {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
}

beforeEach(() => {
  globalThis.window = { addEventListener() {}, removeEventListener() {}, dispatchEvent() {} };
  globalThis.localStorage = fakeLocalStorage();
  globalThis.window.localStorage = globalThis.localStorage;
});

function storeLegacy(prefs) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

describe("loadProfile", () => {
  it("is the shipped defaults for an account that never opened the page", () => {
    expect(loadProfile()).toEqual({ ...PROFILE_DEFAULTS });
  });

  it("survives a corrupt cache rather than throwing on a settings page", () => {
    localStorage.setItem(PROFILE_KEY, "{not json");
    expect(loadProfile()).toEqual({ ...PROFILE_DEFAULTS });
  });

  it("falls back to the default voice for a preset it does not recognise", () => {
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ writing_preset: "oracular" }));
    expect(loadProfile().writing_preset).toBe("practitioner");
  });
});

describe("migrateLegacyPreferences", () => {
  it("carries nothing when there was no old profile", () => {
    expect(migrateLegacyPreferences()).toBeNull();
  });

  it("keeps the voice the dialog was set to", () => {
    storeLegacy({ communication_style: "technical", report_depth: "detailed" });
    expect(migrateLegacyPreferences()).toEqual({ writing_preset: "technical" });
  });

  it("turns the outcome enum into a sentence instead of dropping it", () => {
    // The control is gone; the intent behind it is not, and a four-way radio
    // group was always a flattened version of this sentence.
    storeLegacy({ primary_outcome: "revenue" });
    expect(migrateLegacyPreferences().notes).toBe("Weight findings toward revenue and growth.");
  });

  it("does not write the same sentence twice on a second visit", () => {
    storeLegacy({ primary_outcome: "risk" });
    const first = migrateLegacyPreferences();
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ ...PROFILE_DEFAULTS, ...first }));
    storeLegacy({ primary_outcome: "risk" });
    expect(migrateLegacyPreferences()).toBeNull();
  });

  it("never overwrites something already on the profile", () => {
    localStorage.setItem(
      PROFILE_KEY,
      JSON.stringify({ ...PROFILE_DEFAULTS, role: "Founder / CEO" }),
    );
    storeLegacy({ role: "Growth Manager" });
    expect(migrateLegacyPreferences()).toBeNull();
  });

  it("clears the fields the profile now owns, and leaves the per-run dials alone", () => {
    storeLegacy({
      role: "Product Manager",
      primary_outcome: "quality",
      thinking: "deep",
      tier: "heavy",
      context_compression: false,
    });
    migrateLegacyPreferences();
    const left = loadPreferences();
    // Retired: gone from the blob, not lingering as "".
    expect(left.primary_outcome).toBeUndefined();
    // Back as a composer dial, so an old choice is kept rather than dropped.
    expect(left.preferred_artifact_format).toBe("html");
    // Still per-device, still written by the composer, not by the profile.
    expect(left.thinking).toBe("deep");
    expect(left.tier).toBe("heavy");
    expect(left.context_compression).toBe(false);
  });

  it("cannot carry more notes than the prompt budget allows", () => {
    localStorage.setItem(
      PROFILE_KEY,
      JSON.stringify({ ...PROFILE_DEFAULTS, notes: "x".repeat(NOTES_MAX_CHARS - 5) }),
    );
    storeLegacy({ primary_outcome: "efficiency" });
    expect(migrateLegacyPreferences().notes.length).toBe(NOTES_MAX_CHARS);
  });
});

describe("the request payload a signed-out run sends", () => {
  it("follows the page, since there is no row for the server to prefer", async () => {
    const { saveProfile } = await import("../userProfile.js");
    await saveProfile({ writing_preset: "executive", role: "Founder / CEO" });
    const sent = loadPreferences();
    expect(sent.role).toBe("Founder / CEO");
    expect(sent.communication_style).toBe("executive");
    expect(sent.report_depth).toBe("summary");
  });
});

describe("timezone", () => {
  // The list comes from `Intl.supportedValuesOf` rather than a copy kept in the
  // repo, because the tz database moves and a copy is wrong from the first
  // release after someone splits a zone. What is worth pinning is that the
  // helpers around it survive a browser that answers oddly — a settings page
  // that throws is worse than one offering a short list.

  it("offers the platform's zones, and enough of them to be the real list", () => {
    const zones = listTimezones();
    expect(zones).toContain("Europe/Madrid");
    expect(zones.length).toBeGreaterThan(100);
  });

  it("falls back rather than rendering no control when Intl cannot answer", () => {
    const real = Intl.supportedValuesOf;
    Intl.supportedValuesOf = () => {
      throw new Error("locked down");
    };
    try {
      const zones = listTimezones();
      expect(zones).toContain("UTC");
      expect(zones.length).toBeGreaterThan(0);
    } finally {
      Intl.supportedValuesOf = real;
    }
  });

  it("names the city and groups on the region, so 420 entries stay type-ahead-able", () => {
    expect(zoneLabel("Europe/Madrid")).toBe("Madrid");
    expect(zoneRegion("Europe/Madrid")).toBe("Europe");
    expect(zoneLabel("America/Argentina/Buenos_Aires")).toBe("Argentina / Buenos Aires");
  });

  it("groups a bare zone under Other rather than under itself", () => {
    expect(zoneRegion("UTC")).toBe("Other");
    expect(zoneLabel("UTC")).toBe("UTC");
  });

  it("reports an offset for the hint, and nothing for an unset zone", () => {
    expect(zoneOffsetLabel("Europe/Madrid")).toMatch(/GMT[+-]\d/);
    expect(zoneOffsetLabel("")).toBe("");
    expect(zoneOffsetLabel("Middle/Earth")).toBe("");
  });

  it("detects a zone without throwing", () => {
    expect(typeof detectTimezone()).toBe("string");
  });

  it("is empty on a profile nobody has set one on", () => {
    expect(PROFILE_DEFAULTS.timezone).toBe("");
    expect(loadProfile().timezone).toBe("");
  });

  it("survives the cache holding a non-string", () => {
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ timezone: 42 }));
    expect(loadProfile().timezone).toBe("42");
  });
});
