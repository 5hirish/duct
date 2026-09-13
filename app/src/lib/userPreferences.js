export const PREFS_KEY = "duct_user_preferences";

// What is left here after the profile moved to the server
// (`lib/userProfile.js`): the three per-run dials the composer writes, which
// are per-device on purpose — "think harder on this laptop" is a statement
// about this session, not about the person.
//
// `role`, `communication_style` and `report_depth` are still sent on each
// agent request for older clients and signed-out runs, seeded from the profile
// rather than edited here. `primary_outcome` and `preferred_artifact_format`
// are gone: the first folds into the profile's notes on upgrade
// (`migrateLegacyPreferences`), the second was a per-artifact choice that both
// server call sites already default.
export const PREFS_DEFAULTS = {
  role: "",
  communication_style: "practitioner",
  report_depth: "balanced",
  // How hard the model should think, in Duct's four rungs rather than the
  // provider's words. "" means the model's own default — see the note in
  // backend/agents/thinking.py for why that is not normalised away.
  thinking: "",
  // Which tier the run's main job starts on: "heavy" | "standard" | "light",
  // or "" for Duct's own job→tier pick (backend/agents/tiers.py). A lift only
  // moves the starting rung; a tier that cannot run still steps down.
  tier: "",
  // Whether connector rows reach the model folded to a compact table instead
  // of raw JSON. On by default because off is not "the model sees everything":
  // off is the mid-structure cut in backend/agents/insights/data_tools.py,
  // which drops rows from a large pull. The fold is lossless and verified per
  // payload, so this changes how rows are written, never which numbers they
  // carry.
  context_compression: true,
};

export function loadPreferences() {
  if (typeof window === "undefined") return { ...PREFS_DEFAULTS };
  try {
    return { ...PREFS_DEFAULTS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
  } catch {
    return { ...PREFS_DEFAULTS };
  }
}

export function savePreferences(prefs) {
  const value = JSON.stringify(prefs);
  localStorage.setItem(PREFS_KEY, value);
  window.dispatchEvent(
    new StorageEvent("storage", { key: PREFS_KEY, newValue: value, storageArea: localStorage })
  );
}

