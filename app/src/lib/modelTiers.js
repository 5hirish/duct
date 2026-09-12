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
  },
  {
    key: "standard",
    label: "Standard",
    icon: "scale",
    tagline: "Most of what runs",
  },
  {
    key: "light",
    label: "Light",
    icon: "feather",
    tagline: "High volume, low judgement",
  },
];

/**
 * What to call a model on screen.
 *
 * Comes from the catalogue so it cannot drift from what actually runs. `label`
 * is absent for a model the backend has not named yet, and the id is the right
 * fallback — it is what the user would paste into a support thread.
 */
export function modelLabel(model) {
  return model?.label || model?.id || "";
}


export const TIER_KEYS = TIERS.map((tier) => tier.key);

export function getTier(key) {
  return TIERS.find((tier) => tier.key === key) ?? TIERS[1];
}

/**
 * Whose account pays. `source` comes from `/providers/status`.
 *
 * "Duct's key" used to cover both a self-hosted env file and our hosted
 * account, which are the same config field and opposite answers to the only
 * question the chip exists to answer. The backend now splits them.
 *
 * Two rules these labels have to keep, both learned the hard way:
 *
 * 1. **Say the vendor, not the category.** `subscription` read "Your
 *    subscription", which is true of whichever tile it lands on — so when a
 *    bug put it on Anthropic, the chip was still grammatical and nobody could
 *    see it was lying. "Your ChatGPT plan" is wrong out loud on any other
 *    tile, which is the point.
 * 2. **Only `user` and `stored` are green.** Those are the two the reader did
 *    something to get. `env` is a key that happens to be on the machine and
 *    `cloud` is ours; both make a run possible, neither is an answer to "have
 *    I set this up", and four green ticks under a heading that says "bring
 *    your own keys" reads as done when nothing has been brought.
 */
export const SOURCE_LABELS = {
  user: "Your key",
  stored: "Your saved key",
  env: "This computer's key",
  cloud: "Duct's key",
  subscription: "Your ChatGPT plan",
  none: "Not set",
};

/**
 * The same fact as a whole sentence, for the one place it is said for the
 * entire page rather than pinned to a tile.
 *
 * SOURCE_DETAIL is written as a clause because it lands in a `title=`; read
 * on its own under the summary card it is a fragment, and a fragment is what
 * a sentence written for somewhere else always sounds like.
 */
export const SOURCE_SENTENCE = {
  user: "Running on the key you pasted — this browser session only.",
  stored: "Running on your saved key, the one that also funds scheduled runs.",
  env: "Running on a key already on this computer, not one you added here.",
  cloud: "Running on Duct's own key — we are paying for these runs.",
  subscription: "Running on the ChatGPT plan you signed in with on this desktop.",
  none: "No key set for these models yet.",
};

/** Longer form, for the provider tiles where there is room for a clause. */
export const SOURCE_DETAIL = {
  user: "Using the key you pasted — this browser session only",
  stored: "Using your saved key — the one that also funds scheduled runs",
  env: "Using a key already on the machine running Duct, not one you added here",
  cloud: "Using Duct's own key — we're paying for this run",
  subscription: "Using the ChatGPT plan you signed in with on this desktop",
  none: "No key set",
};

/** Green is reserved for a key the reader put there themselves. */
export const SOURCE_TONE = {
  user: "ok",
  stored: "ok",
  env: "info",
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
  xai: "xai",
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

/**
 * The one answer to "whose key pays" when all three tiers give the same one,
 * and `""` when they do not.
 *
 * Three callers ask, for three reasons, and they must not disagree: the
 * summary says the answer once when there is one, the tier cards say it
 * per-card when there is not, and the Images row stays silent when its own
 * answer is the one already on screen. Written as the *value* rather than as
 * a boolean because two of those three need to print it, and a predicate plus
 * a separate lookup is how the page ends up both saying it once and saying it
 * four times.
 *
 * `""` while any tier is unresolved: "they agree" is a claim, and three
 * pending answers are not three matching ones.
 */
export function agreedSource(previewByTier = {}, providersById = {}) {
  const sources = TIER_KEYS.map(
    (key) => providersById[previewByTier[key]?.provider]?.source
  ).filter(Boolean);
  if (sources.length !== TIER_KEYS.length) return "";
  return new Set(sources).size === 1 ? sources[0] : "";
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

/** What `fetchProviderStatus` answers when the server cannot be asked. */
const NO_PROVIDER_STATUS = Object.freeze({ providers: [], images: null, chatgptAuthEnabled: false });

/**
 * Which providers this browser can actually reach, and which one would draw.
 *
 * Sends the `X-Provider-*` headers deliberately: the honest answer is the
 * union of the customer's keys and the server's, and only the server sees
 * both. `images` is the server's pick for the image tools — provider, model,
 * source — computed from the same tiles by the same preference order the
 * run uses, so the Images row never claims a backend the run would not.
 * On failure returns no providers and no image pick, and the page degrades
 * to showing models without credential chips rather than claiming
 * everything is broken.
 */
export async function fetchProviderStatus() {
  try {
    const res = await fetch(`${BASE}/api/providers/status`, {
      headers: { ...backendAuthedHeaders(), ...(await providerKeyHeaders()) },
    });
    if (!res.ok) return NO_PROVIDER_STATUS;
    const payload = await res.json();
    return {
      providers: payload.providers ?? [],
      images: payload.images ?? null,
      // The backend's kill switch for "Continue with ChatGPT". Absent on an
      // older backend, which never offered the path, so absent means off.
      chatgptAuthEnabled: payload.chatgpt_auth_enabled === true,
    };
  } catch {
    return NO_PROVIDER_STATUS;
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
