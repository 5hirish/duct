/**
 * Google Ads request identifiers (client-side).
 *
 * This file used to hold a bring-your-own developer token, because Duct's own
 * token was pending Google approval and a user's approved token was what
 * unlocked their production accounts. Google sunset developer tokens on
 * 2026-09-09: the header is ignored by the API servers, and a call's access
 * level is now the access level of the Cloud project that owns Duct's OAuth
 * client. A pasted token bought nothing after that, so the whole store is
 * gone — keeping it would have left users a knob that silently does nothing.
 *
 * What remains is the MCC id, which the sunset does not touch: it still tells
 * the API which manager account to read child accounts through. It is an
 * account identifier, not a secret, so plain `sessionStorage` on every shell.
 */

const SS_LOGIN_CUSTOMER_ID = "gads_login_customer_id";

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

/** Request fields for a Google Ads call, ready to spread into a body. */
export function googleAdsRequestFields() {
  return { login_customer_id: getAdsLoginCustomerId() };
}
