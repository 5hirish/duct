/**
 * Cookie consent: the rule, and what the user decided. Never the vendor.
 *
 * Analytics storage is not exempt under ePrivacy Art 5(3), or Spain's LSSI
 * Art 22.2, so measurement waits on a decision instead of an idle callback.
 * This mirrors `site/assets/duct.js` deliberately — one product, one consent
 * story, whichever surface someone lands on first.
 *
 * What a refusal *does* belongs to the provider (`lib/analytics/`): for GTM it
 * means the container never loads at all rather than running in cookieless ping
 * mode, because "we sent nothing" needs no defending. Nothing in this file
 * knows that, which is the point — a fork that swaps the provider should not
 * have to re-derive the law.
 */

/** Any surface can reopen the question by dispatching this on `window`. */
export const CONSENT_SETTINGS_EVENT = "duct:consent-settings";

export const CONSENT_GRANTED = "granted";
export const CONSENT_DENIED = "denied";

const CHOICE_KEY = "duct_consent";

/**
 * Six months, then ask again. Consent does not last forever, and the CNIL's six
 * is the shorter of the two numbers we are answerable to.
 */
const CONSENT_TTL_DAYS = 180;
const REGION_KEY = "duct_consent_region";

/**
 * EEA + UK + Switzerland. Switzerland is not EEA, but the revised FADP asks the
 * same question and the answer costs one array entry.
 */
const CONSENT_REGIONS = new Set(
  ("AT BE BG HR CY CZ DK EE FI FR DE GR HU IS IE IT LV LI LT " +
    "LU MT NL NO PL PT RO SK SI ES SE GB CH").split(" "),
);

/**
 * Safari's private mode throws on write, and a lost preference means we ask
 * again — the safe direction to fail in.
 */
function readStore(store, key) {
  try {
    return window[store].getItem(key);
  } catch {
    return null;
  }
}

function writeStore(store, key, value) {
  try {
    window[store].setItem(key, value);
  } catch {
    /* no-op */
  }
}

/**
 * The registrable domain, so one answer covers getduct.ai, app.getduct.ai and
 * the desktop shell (which loads app.getduct.ai).
 */
function consentDomain() {
  const labels = (window.location?.hostname || "").split(".");
  return labels.length >= 2 ? `.${labels.slice(-2).join(".")}` : labels.join(".");
}

/**
 * The choice is a cookie rather than localStorage, because localStorage is
 * per-origin: the marketing site and the app would each ask the same person the
 * same question. One journey, one answer.
 *
 * The cookie is strictly necessary and needs no consent of its own: it exists to
 * record a refusal just as much as an acceptance.
 */
export function readConsentChoice() {
  if (typeof window === "undefined") return null;
  const match = new RegExp(`(?:^|; )${CHOICE_KEY}=([^;]*)`).exec(document.cookie || "");
  return match ? decodeURIComponent(match[1]) : null;
}

export function storeConsentChoice(choice) {
  if (typeof window === "undefined") return;
  const expires = new Date(Date.now() + CONSENT_TTL_DAYS * 864e5).toUTCString();
  document.cookie =
    `${CHOICE_KEY}=${choice}; expires=${expires}; path=/; domain=${consentDomain()}` +
    `; SameSite=Lax${window.location.protocol === "https:" ? "; Secure" : ""}`;
}

/**
 * Cloudflare serves `/cdn-cgi/trace` on every proxied zone, so the visitor's
 * country costs one cached request and no third-party geo service.
 *
 * Every failure path — no network, a non-OK response, an unparseable body —
 * resolves to `true`. Guessing wrong in the other direction is the one that
 * stores something it had no right to store.
 */
export async function consentRequired() {
  const cached = readStore("sessionStorage", REGION_KEY);
  if (cached) return CONSENT_REGIONS.has(cached);

  try {
    const response = await fetch("/cdn-cgi/trace", { credentials: "omit" });
    if (!response.ok) return true;
    const match = /(?:^|\n)loc=([A-Z]{2})/.exec(await response.text());
    if (!match) return true;
    writeStore("sessionStorage", REGION_KEY, match[1]);
    return CONSENT_REGIONS.has(match[1]);
  } catch {
    return true;
  }
}
