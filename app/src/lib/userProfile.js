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

import { msg } from "@lingui/core/macro";
import { BASE } from "./api";
import { authedHeaders, hasAuthToken } from "./authFetch";
import { writeLocaleCookie } from "../i18n/cookie";
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
  // "" reads as UTC, which is what every date window resolved to before this
  // field existed. The page offers the browser's own zone as a one-click fix
  // rather than pre-selecting it: a detected value saved without being chosen
  // is indistinguishable from a preference, and this one changes which seven
  // days "last week" means.
  timezone: "",
  // A catalogue tag from `i18n/locales.js` ("es", "pt-BR", ...) or "" for
  // "follow the browser". The interface, not the model: see that file for
  // why it is not the same list as LANGUAGES below.
  interface_language: "",
  notes: "",
});

/** How Duct writes. The order is the order the page shows them in. */
export const WRITING_PRESETS = [
  {
    value: "executive",
    label: msg`Executive`,
    description: msg`Impact and money first, few actions, no jargon`,
  },
  {
    value: "practitioner",
    label: msg`Practitioner`,
    description: msg`The signal, the number behind it, what to do next`,
  },
  {
    value: "technical",
    label: msg`Technical`,
    description: msg`Every measurement, the method, notes for whoever builds the fix`,
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
  { value: "", label: msg`Match my messages` },
  { value: "English", label: msg`English` },
  { value: "Spanish", label: msg`Español` },
  { value: "French", label: msg`Français` },
  { value: "German", label: msg`Deutsch` },
  { value: "Portuguese", label: msg`Português` },
  { value: "Italian", label: msg`Italiano` },
  { value: "Dutch", label: msg`Nederlands` },
  { value: "Hindi", label: msg`हिन्दी` },
  { value: "Japanese", label: msg`日本語` },
];

/**
 * Every IANA zone the browser knows, newest tzdata included, grouped by region.
 *
 * From `Intl.supportedValuesOf` rather than a list kept here or a package:
 * the tz database moves — zones get added, renamed and merged — and a copy in
 * this file is a copy that is wrong from the first release after someone
 * splits one. The platform's list is the platform's problem to keep current.
 *
 * Falls back to a short list on a browser too old for `supportedValuesOf`
 * (and on the server, where there is no `Intl` catalogue to ask), because a
 * profile page that renders no timezone control at all is worse than one
 * offering a dozen.
 */
const FALLBACK_ZONES = [
  "UTC",
  "Europe/London",
  "Europe/Madrid",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

export function listTimezones() {
  try {
    const zones = Intl.supportedValuesOf?.("timeZone");
    if (Array.isArray(zones) && zones.length) return zones;
  } catch {
    /* older browser, or a locked-down Intl — fall through */
  }
  return FALLBACK_ZONES;
}

/** The zone this browser is in, or "" when it cannot say. */
export function detectTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

/** "Europe/Madrid" → "Madrid" — the region is the group heading. */
export function zoneLabel(zone) {
  const tail = String(zone || "").split("/").slice(1).join(" / ");
  return (tail || zone).replace(/_/g, " ");
}

/** "Europe/Madrid" → "Europe"; a bare zone like "UTC" groups under "Other". */
export function zoneRegion(zone) {
  const head = String(zone || "").split("/")[0];
  return head && head !== zone ? head.replace(/_/g, " ") : "Other";
}

/** The current UTC offset, for the hint beside the control. Never throws. */
export function zoneOffsetLabel(zone, now = new Date()) {
  if (!zone) return "";
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      timeZoneName: "shortOffset",
    }).formatToParts(now);
    return parts.find((p) => p.type === "timeZoneName")?.value || "";
  } catch {
    return "";
  }
}

export const ROLE_OPTIONS = [
  { value: "", label: msg`Not saying` },
  { value: "Founder / CEO", label: msg`Founder / CEO` },
  { value: "Executive (CMO, VP, Director)", label: msg`Executive (CMO, VP, Director)` },
  { value: "Product Manager", label: msg`Product Manager` },
  { value: "Growth Manager", label: msg`Growth Manager` },
  { value: "SEO / Content Lead", label: msg`SEO / Content Lead` },
  { value: "Developer / Engineer", label: msg`Developer / Engineer` },
  { value: "Consultant / Agency", label: msg`Consultant / Agency` },
  { value: "Other", label: msg`Other` },
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
    timezone: String(body?.timezone || ""),
    interface_language: String(body?.interface_language || ""),
    notes: String(body?.notes || "").slice(0, NOTES_MAX_CHARS),
  };
}

/**
 * Keep the locale cookie in step with the profile.
 *
 * The root layout is a server component and reads the cookie, not the
 * profile, so every place the profile lands in the browser (first fetch,
 * every save) writes the cookie. Returns true when the cookie changed, which
 * is the caller's cue to `router.refresh()` so the frame re-renders in the
 * new language — only when the value actually moved, because a refresh on
 * every profile fetch would re-render the whole tree on every page load.
 */
export function mirrorInterfaceLanguage(profile) {
  if (!profile || !profile.interface_language) return false;
  return writeLocaleCookie(profile.interface_language);
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
 * The enum that was cut is not dropped silently: `primary_outcome` becomes a
 * sentence in the notes, which is where that intent belongs anyway.
 * `preferred_artifact_format` stays in the blob: it is a composer dial again.
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

  // The retired control leaves the old blob entirely rather than being
  // blanked: a key that is gone from the model should not linger as "". What
  // stays is what the composer writes here — thinking, tier, format,
  // context_compression — plus the three fields a signed-out request carries,
  // which `mirrorToRequestPayload` keeps in step from now on.
  try {
    const { primary_outcome, ...keep } = prefs;
    savePreferences(keep);
  } catch {
    /* the profile write below is what matters */
  }
  return patch;
}
