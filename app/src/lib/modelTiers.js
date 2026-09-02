/**
 * The three models a user picks, and how the app reads them back.
 *
 * Mirrors `backend/agents/tiers.py` — keep the tier keys in sync. What is
 * deliberately *not* mirrored here is the resolution: which model actually
 * serves a job, and what happens when a tier has no key, is answered by
 * `POST /api/models/preview` on the server. The page prints a promise
 * ("Light jobs run on Claude Sonnet 5 until you add an OpenAI key"), and a
 * promise computed in the browser from whichever keys this tab happens to hold
 * would drift the first time the resolver gained a rule.
 *
 * Storage is `localStorage`, beside `duct_engine` and `duct_user_preferences`,
 * because this is a per-user preference and not a per-project one. An absent
 * tier means "unset" and resolves to the backend's default — so an empty map is
 * byte-for-byte today's behaviour, which is what makes shipping this a no-op
 * for every existing install.
 */

import { BASE, backendAuthedHeaders } from "./api";
import { providerKeyHeaders } from "./providerKeys";

export const MODEL_MAP_STORAGE_KEY = "duct_model_map";

/** Fired on save so other surfaces (the composer) can re-read without a reload. */
export const MODEL_MAP_CHANGED = "duct:model-map-changed";

/**
 * Named Heavy / Standard / Light, not Intelligent / Balanced / Quick.
 *
 * The icons run the same metaphor the names do — an anvil, a balance scale and
 * a feather — so the three cards are told apart by shape before anyone reads a
 * word, and the ordering is legible without a number.
 *
 * `agents/thinking.py` already owns a user-facing four-rung dial labelled
 * Quick, Balanced, Deep and Exhaustive, and both controls sit in the same
 * composer. Tier and thinking are orthogonal — a Heavy model can run at Quick
 * thinking — so two dials sharing words would read as one duplicated dial.
 */
export const TIERS = [
  {
    key: "heavy",
    label: "Heavy",
    icon: "anvil",
    tagline: "The work you act on",
    blurb: "Slow and expensive on purpose. Reserved for the analysis that becomes your decision.",
  },
  {
    key: "standard",
    label: "Standard",
    icon: "scale",
    tagline: "Most of what runs",
    blurb: "Real reasoning at ordinary cost. Where Duct spends most of its time.",
    fallbackFor: "heavy",
  },
  {
    key: "light",
    label: "Light",
    icon: "feather",
    tagline: "High volume, low judgement",
    blurb: "Reading pages, remembering context, naming things. Should be the cheapest model you own.",
    fallbackFor: "standard",
  },
];

export const TIER_KEYS = TIERS.map((tier) => tier.key);

export function getTier(key) {
  return TIERS.find((tier) => tier.key === key) ?? TIERS[1];
}

/**
 * What each internal job is, in words a growth marketer recognises.
 *
 * The backend's `Job` enum names steps for what they produce; these are the
 * same steps described by what the user would see. Shown only inside the
 * "what runs here" disclosure — this is an explanation, not a control.
 */
export const JOB_LABELS = {
  analysis: "Writes your brief",
  audit: "Scores your site",
  verification: "Proves a number before it's used",
  synthesis: "Structures the findings",
  drafting: "Writes content and captions",
  chat: "Answers your follow-up questions",
  research: "Reads pages and connector data",
  memory: "Remembers context between sessions",
  recap: "Summaries and titles",
};

/**
 * Whose account pays. `source` comes from `/providers/status`.
 *
 * "Duct's key" used to cover both a self-hosted env file and our hosted
 * account, which are the same config field and opposite answers to the only
 * question the chip exists to answer. The backend now splits them.
 */
export const SOURCE_LABELS = {
  user: "Your key",
  stored: "Your saved key",
  env: "From env",
  cloud: "Duct cloud",
  subscription: "Your subscription",
  none: "Not set",
};

/** Longer form, for the provider tiles where there is room for a clause. */
export const SOURCE_DETAIL = {
  user: "Using the key you provided",
  stored: "Using your saved key — also serves scheduled runs",
  env: "Using a key from this instance's environment",
  cloud: "Using Duct's hosted key — our account is paying",
  subscription: "Using your Claude subscription on this machine",
  none: "No key set",
};

/** A source that costs the user nothing is worth showing differently. */
export const SOURCE_TONE = {
  user: "ok",
  stored: "ok",
  env: "ok",
  cloud: "info",
  subscription: "ok",
  none: "warn",
};

/**
 * Backend provider id → the key its mark is filed under in `connections/logos`.
 *
 * They agree everywhere except Google, whose provider id is `google_genai`
 * and whose logo is the Gemini mark. One map beats a special case at each of
 * the four places a logo is drawn.
 */
export const PROVIDER_LOGO_KEY = {
  anthropic: "anthropic",
  openai: "openai",
  google_genai: "gemini",
  openrouter: "openrouter",
};

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

/** The saved map, or `{}` when nothing has been set. Never throws. */
export function loadModelMap() {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(MODEL_MAP_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

/** Persist and notify. Pass `{}` to clear back to the shipped defaults. */
export function saveModelMap(map) {
  if (typeof window === "undefined") return;
  try {
    const empty = !map || Object.keys(map).length === 0;
    if (empty) window.localStorage.removeItem(MODEL_MAP_STORAGE_KEY);
    else window.localStorage.setItem(MODEL_MAP_STORAGE_KEY, JSON.stringify(map));
    window.dispatchEvent(new CustomEvent(MODEL_MAP_CHANGED, { detail: map || {} }));
  } catch {
    /* private mode / storage disabled — the map stays at its defaults */
  }
}

/** The tier picks alone, which is what every agent request carries. */
export function tierPicks(map = loadModelMap()) {
  const tiers = map?.tiers || {};
  return TIER_KEYS.reduce((acc, key) => {
    if (tiers[key]) acc[key] = tiers[key];
    return acc;
  }, {});
}

/**
 * The `models` field for an agent request body.
 *
 * Returns `undefined` when nothing is configured, so an untouched install
 * sends exactly the payload it sends today.
 */
export function modelPayload(map = loadModelMap()) {
  const tiers = tierPicks(map);
  const modality = map?.modality || {};
  const hasModality = Object.keys(modality).length > 0;
  if (!Object.keys(tiers).length && !hasModality) return undefined;
  return { tiers, ...(hasModality ? { modality } : {}) };
}

// ---------------------------------------------------------------------------
// Server reads
// ---------------------------------------------------------------------------

/**
 * Which providers this browser can actually reach.
 *
 * Sends the `X-Provider-*` headers deliberately: the honest answer is the
 * union of the customer's keys and the server's, and only the server sees
 * both. On failure returns `[]`, and the page degrades to showing models
 * without credential chips rather than claiming everything is broken.
 */
export async function fetchProviderStatus() {
  try {
    const res = await fetch(`${BASE}/api/providers/status`, {
      headers: { ...backendAuthedHeaders(), ...(await providerKeyHeaders()) },
    });
    if (!res.ok) return [];
    const payload = await res.json();
    return payload.providers ?? [];
  } catch {
    return [];
  }
}

/**
 * The model list, tier defaults and job assignment — all server-owned.
 *
 * Nothing here is hard-coded in the bundle on purpose. The Engine dialog this
 * page replaces advertised `defaultModel: "Gemini 2.5 Flash"` as a literal
 * string, and it had been wrong for two catalogue generations.
 */
export async function fetchModelCatalogue() {
  try {
    const res = await fetch(`${BASE}/api/models/catalogue`, { headers: backendAuthedHeaders() });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** What a draft map would actually run, resolved by the code that will run it. */
export async function fetchTierPreview(tiers, engine) {
  try {
    const res = await fetch(`${BASE}/api/models/preview`, {
      method: "POST",
      headers: {
        ...backendAuthedHeaders({ "Content-Type": "application/json" }),
        ...(await providerKeyHeaders()),
      },
      body: JSON.stringify({ tiers: tiers || {}, engine: engine || "" }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
