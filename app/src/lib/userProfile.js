"use client";

/**
 * The operator's profile, read from and written to the server.
 *
 * Same split as `modelSettings.js`: `localStorage` is a cache so the page
 * paints before the network answers and so a signed-out visitor still gets the
 * voice they picked, and the server row is what every run reads — including
 * the scheduled brief, which has no browser at all. When the two disagree the
 * server wins, because a phone set last week must not be overwritten by a tab
 * that was open before it.
 *
 * Every write is a partial: send the field that changed. A whole-object PUT
 * would let a tab loaded before a change put the old value back on the next
 * save.
 */

import { BASE } from "./api";
import { authedHeaders, hasAuthToken } from "./authFetch";
import { PREFS_KEY, loadPreferences, savePreferences } from "./userPreferences";

const ENDPOINT = `${BASE}/api/user/profile`;

/** Local cache of the server row, so the page never paints empty. */
export const PROFILE_KEY = "duct_user_profile";

/** Fired after a successful save, so other surfaces can re-read. */
export const PROFILE_CHANGED = "duct:profile-changed";

/** Mirrors `service/profile.py`: the free text rides in every prompt. */
export const NOTES_MAX_CHARS = 1000;

export const PROFILE_DEFAULTS = Object.freeze({
  display_name: "",
  role: "",
  // One control where there were two. `service/profile.py` derives the older
  // communication_style/report_depth pair from it, so nothing downstream had
  // to change when the page did.
  writing_preset: "practitioner",
  // "" means "match the language I wrote in" — right more often than any fixed
  // choice, and it never makes someone set a preference to keep the behaviour
  // they already had.
  communication_language: "",
  notes: "",
});

/** How Duct writes. The order is the order the page shows them in. */
export const WRITING_PRESETS = [
  {
    value: "executive",
    label: "Executive",
    description: "Impact and money first, few actions, no jargon",
  },
  {
    value: "practitioner",
    label: "Practitioner",
    description: "The signal, the number behind it, what to do next",
  },
  {
    value: "technical",
    label: "Technical",
    description: "Every measurement, the method, notes for whoever builds the fix",
  },
];

/**
 * The languages offered by name, plus "match my messages" as the default.
 *
 * A list rather than free text because this value goes into a prompt: "Write
 * in {value}" with a typo in it is a worse failure than a missing language,
 * and it fails silently in a deliverable somebody forwards.
 */
export const LANGUAGES = [
  { value: "", label: "Match my messages" },
  { value: "English", label: "English" },
  { value: "Spanish", label: "Español" },
  { value: "French", label: "Français" },
  { value: "German", label: "Deutsch" },
  { value: "Portuguese", label: "Português" },
  { value: "Italian", label: "Italiano" },
  { value: "Dutch", label: "Nederlands" },
  { value: "Hindi", label: "हिन्दी" },
  { value: "Japanese", label: "日本語" },
];

export const ROLE_OPTIONS = [
  { value: "", label: "Not saying" },
  { value: "Founder / CEO", label: "Founder / CEO" },
  { value: "Executive (CMO, VP, Director)", label: "Executive (CMO, VP, Director)" },
  { value: "Product Manager", label: "Product Manager" },
  { value: "Growth Manager", label: "Growth Manager" },
  { value: "SEO / Content Lead", label: "SEO / Content Lead" },
  { value: "Developer / Engineer", label: "Developer / Engineer" },
  { value: "Consultant / Agency", label: "Consultant / Agency" },
  { value: "Other", label: "Other" },
];

function coerce(body) {
  const preset = WRITING_PRESETS.some((p) => p.value === body?.writing_preset)
    ? body.writing_preset
    : PROFILE_DEFAULTS.writing_preset;
  return {
    display_name: String(body?.display_name || ""),
    role: String(body?.role || ""),
    writing_preset: preset,
    communication_language: String(body?.communication_language || ""),
    notes: String(body?.notes || "").slice(0, NOTES_MAX_CHARS),
  };
}

/** The cached copy, for the first paint. Never throws. */
export function loadProfile() {
  if (typeof window === "undefined") return { ...PROFILE_DEFAULTS };
  try {
    return coerce({ ...PROFILE_DEFAULTS, ...JSON.parse(localStorage.getItem(PROFILE_KEY) || "{}") });
  } catch {
    return { ...PROFILE_DEFAULTS };
  }
}

function cache(profile) {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch {
    /* private mode — the server copy is still the truth */
  }
}

/**
 * The saved profile. Falls back to the cache, then the defaults.
 *
 * Never throws: this paints a settings page, not a run, and a page that fails
 * to render because a preference endpoint was slow is the worse outcome.
 */
export async function fetchProfile() {
  if (!hasAuthToken()) return loadProfile();
  try {
    const res = await fetch(ENDPOINT, { headers: authedHeaders() });
    if (!res.ok) return loadProfile();
    const profile = coerce(await res.json());
    cache(profile);
    return profile;
  } catch {
    return loadProfile();
  }
}

/**
 * Persist the fields given. Returns what the server now holds, or null when it
 * could not be reached, so the caller can keep its optimistic state and say so.
 */
export async function saveProfile(patch) {
  const next = coerce({ ...loadProfile(), ...(patch || {}) });
  cache(next);
  mirrorToRequestPayload(next);
  if (!hasAuthToken()) return null;
  try {
    const res = await fetch(ENDPOINT, {
      method: "PUT",
      headers: { ...authedHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(patch || {}),
    });
    if (!res.ok) return null;
    const profile = coerce(await res.json());
    cache(profile);
    window.dispatchEvent(new CustomEvent(PROFILE_CHANGED, { detail: profile }));
    return profile;
  } catch {
    return null;
  }
}

/**
 * Keep the three fields the agent request still carries in step with the page.
 *
 * A signed-out run has no row for the server to read, so `resolve` falls back
 * to what the browser sent — and what the browser sends comes from
 * `duct_user_preferences`, not from here. Without this mirror, the one person
 * whose profile exists only in a browser is the one whose profile the run
 * ignores.
 */
function mirrorToRequestPayload(profile) {
  const pair = {
    executive: ["executive", "summary"],
    practitioner: ["practitioner", "balanced"],
    technical: ["technical", "detailed"],
  }[profile.writing_preset] || ["practitioner", "balanced"];
  try {
    savePreferences({
      ...loadPreferences(),
      role: profile.role,
      communication_style: pair[0],
      report_depth: pair[1],
    });
  } catch {
    /* the server row is the real home; this is a courtesy for signed-out runs */
  }
}

// ---------------------------------------------------------------------------
// One-time carry-over from the dialog this page replaces
// ---------------------------------------------------------------------------

/** Where an old `primary_outcome` lands, since the enum is gone. */
const OUTCOME_SENTENCES = {
  revenue: "Weight findings toward revenue and growth.",
  efficiency: "Weight findings toward efficiency and speed.",
  risk: "Weight findings toward risk and compliance.",
  quality: "Weight findings toward quality and standards.",
};

/**
 * Fold whatever the old dialog stored into the new profile, once.
 *
 * The two enums that were cut are not dropped silently: `primary_outcome`
 * becomes a sentence in the notes, which is where that intent belongs anyway.
 * `preferred_artifact_format` does go, because both server call sites already
 * default and a per-artifact choice was never an identity.
 *
 * Returns the patch it applied, or null when there was nothing to carry.
 */
export function migrateLegacyPreferences() {
  if (typeof window === "undefined") return null;
  let prefs;
  try {
    if (!localStorage.getItem(PREFS_KEY)) return null;
    prefs = loadPreferences();
  } catch {
    return null;
  }

  const preset = ["executive", "practitioner", "technical"].includes(prefs.communication_style)
    ? prefs.communication_style
    : PROFILE_DEFAULTS.writing_preset;
  const sentence = OUTCOME_SENTENCES[prefs.primary_outcome] || "";
  const current = loadProfile();
  const patch = {};
  if (!current.role && prefs.role) patch.role = prefs.role;
  if (current.writing_preset === PROFILE_DEFAULTS.writing_preset && preset !== current.writing_preset) {
    patch.writing_preset = preset;
  }
  if (sentence && !current.notes.includes(sentence)) {
    patch.notes = [current.notes, sentence].filter(Boolean).join(" ").slice(0, NOTES_MAX_CHARS);
  }
  if (!Object.keys(patch).length) return null;

  // The two retired controls leave the old blob entirely rather than being
  // blanked: a key that is gone from the model should not linger as "". What
  // stays is what the composer still writes here — thinking, tier,
  // context_compression — plus the three fields a signed-out request carries,
  // which `mirrorToRequestPayload` keeps in step from now on.
  try {
    const { primary_outcome, preferred_artifact_format, ...keep } = prefs;
    savePreferences(keep);
  } catch {
    /* the profile write below is what matters */
  }
  return patch;
}
