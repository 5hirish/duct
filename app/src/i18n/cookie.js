/**
 * The locale cookie, from the browser's side.
 *
 * Written in two places: when the profile loads or changes (the cookie is the
 * profile field's shadow, see `locales.js`), and by the signed-out selector,
 * which has no profile to save to. Read by the root layout on the server.
 * `SameSite=Lax` and no `Secure` flag on purpose: the desktop shell serves
 * the app from a loopback origin where a Secure cookie would never be sent.
 */
import { LOCALE_COOKIE, LOCALE_COOKIE_MAX_AGE, normalizeLocale } from "./locales";

export function readLocaleCookie() {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(new RegExp(`(?:^|; )${LOCALE_COOKIE}=([^;]*)`));
  return match ? normalizeLocale(decodeURIComponent(match[1]), { allowPseudo: true }) : "";
}

/** Set (or with "" clear) the cookie. Returns true when it changed. */
export function writeLocaleCookie(locale) {
  if (typeof document === "undefined") return false;
  const next = normalizeLocale(locale, { allowPseudo: true });
  if (next === readLocaleCookie()) return false;
  const maxAge = next ? LOCALE_COOKIE_MAX_AGE : 0;
  document.cookie = `${LOCALE_COOKIE}=${encodeURIComponent(next)}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
  return true;
}
