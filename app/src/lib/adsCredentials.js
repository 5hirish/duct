/**
 * Bring-your-own Google Ads API credentials (client-side).
 *
 * Duct's own Google Ads developer token is pending Google approval, so users
 * supply their own token from their Google Ads manager account. Mirrors the
 * shell-aware storage in `providerKeys.js` (BYO provider keys branch):
 *   - Web build  → `sessionStorage` (ephemeral, per browser session).
 *   - Desktop (Tauri) → the OS keychain via the generic `*_provider_key`
 *     invoke commands, keyed by `google_ads_developer_token`. Guarded by
 *     `isTauri()` so it never runs in the browser.
 *
 * The token is sent to the backend per request (`developer_token` field on
 * generate/refresh/accounts calls) and is never persisted server-side — the
 * backend prefers a supplied token over its own env fallback. The MCC
 * login-customer-id is an account identifier, not a secret, and stays in
 * `sessionStorage` on every shell.
 */

const KEYCHAIN_PROVIDER_ID = "google_ads_developer_token";
const SS_DEVELOPER_TOKEN = "gads_developer_token";
const SS_LOGIN_CUSTOMER_ID = "gads_login_customer_id";

function isTauri() {
  return typeof window !== "undefined" && Boolean(window.__TAURI__);
}

/** Read the stored developer token. Returns "" when unset or storage is unavailable. */
export async function getAdsDeveloperToken() {
  if (typeof window === "undefined") return "";
  if (isTauri()) {
    try {
      return (await window.__TAURI__.core.invoke("get_provider_key", { provider: KEYCHAIN_PROVIDER_ID })) || "";
    } catch {
      return "";
    }
  }
  try {
    return window.sessionStorage.getItem(SS_DEVELOPER_TOKEN) || "";
  } catch {
    return "";
  }
}

/** Persist (or, when value is blank, remove) the developer token. */
export async function setAdsDeveloperToken(value) {
  if (typeof window === "undefined") return;
  const trimmed = (value || "").trim();
  if (isTauri()) {
    try {
      await window.__TAURI__.core.invoke(trimmed ? "set_provider_key" : "delete_provider_key", {
        provider: KEYCHAIN_PROVIDER_ID,
        key: trimmed,
      });
    } catch {
      /* keychain unavailable — ignore for the web/dev path */
    }
    return;
  }
  try {
    if (trimmed) window.sessionStorage.setItem(SS_DEVELOPER_TOKEN, trimmed);
    else window.sessionStorage.removeItem(SS_DEVELOPER_TOKEN);
  } catch {
    /* storage unavailable (e.g. private mode) — ignore */
  }
}

export async function clearAdsDeveloperToken() {
  return setAdsDeveloperToken("");
}

/** MCC manager account id (digits only). Not a secret — plain sessionStorage. */
export function getAdsLoginCustomerId() {
  if (typeof window === "undefined") return "";
  try {
    return window.sessionStorage.getItem(SS_LOGIN_CUSTOMER_ID) || "";
  } catch {
    return "";
  }
}

export function setAdsLoginCustomerId(value) {
  if (typeof window === "undefined") return;
  const normalized = (value || "").replace(/-/g, "").trim();
  try {
    if (normalized) window.sessionStorage.setItem(SS_LOGIN_CUSTOMER_ID, normalized);
    else window.sessionStorage.removeItem(SS_LOGIN_CUSTOMER_ID);
  } catch {
    /* storage unavailable — ignore */
  }
}

/** Request fields for the BYO Google Ads credentials, ready to spread into a body. */
export async function googleAdsByoCredentials() {
  return {
    developer_token: await getAdsDeveloperToken(),
    login_customer_id: getAdsLoginCustomerId(),
  };
}
