/**
 * The interface languages, and how a request picks one.
 *
 * Kept apart from `lib/userProfile.js`'s LANGUAGES on purpose: that list is
 * what Duct *writes in*, which any language the model speaks qualifies for.
 * This one is what the interface is *translated into*, which only a language
 * with a filled catalogue qualifies for. The two are different questions, and
 * the day they are conflated a user picks Italian and gets an English UI with
 * no explanation.
 */

/** BCP 47 tags, in the order a selector shows them. Must match lingui.config. */
export const LOCALES = Object.freeze([
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "pt-BR", label: "Português (Brasil)" },
  { value: "de", label: "Deutsch" },
  { value: "ja", label: "日本語" },
]);

export const DEFAULT_LOCALE = "en";

/**
 * The cookie the server reads to render the first frame in the right language.
 *
 * The saved profile is the truth, but the root layout is a server component
 * and the profile is fetched by the browser with a bearer token the server
 * never sees. The cookie is that field's shadow: written whenever the profile
 * loads or changes, and by the signed-out selector, which has no profile.
 * A year, because it only ever mirrors a choice that lives elsewhere.
 */
export const LOCALE_COOKIE = "duct_lang";
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

/** The dev-only stretched locale. Never offered; reached via ?lang=pseudo. */
export const PSEUDO_LOCALE = "pseudo";

const KNOWN = new Set(LOCALES.map((l) => l.value));

/** A supported tag or "" — never a guess. */
export function normalizeLocale(value, { allowPseudo = false } = {}) {
  const tag = String(value || "").trim();
  if (!tag) return "";
  if (allowPseudo && tag === PSEUDO_LOCALE) return tag;
  if (KNOWN.has(tag)) return tag;
  // "pt" and "pt-PT" both read Brazilian Portuguese better than English;
  // "es-MX" is Spanish. Match on the language subtag, then on our tag's.
  const lang = tag.toLowerCase().split("-")[0];
  const match = LOCALES.find((l) => l.value.toLowerCase().split("-")[0] === lang);
  return match ? match.value : "";
}

/**
 * The best locale from an Accept-Language header, or "".
 *
 * First supported language in the browser's own order; the q-weights are
 * already reflected in that order by every browser that sends them.
 */
export function localeFromAcceptLanguage(header) {
  for (const part of String(header || "").split(",")) {
    const tag = part.split(";")[0].trim();
    const locale = normalizeLocale(tag);
    if (locale) return locale;
  }
  return "";
}

/** Cookie, then the browser's languages, then English. */
export function resolveLocale({ cookie, acceptLanguage, allowPseudo = false } = {}) {
  return (
    normalizeLocale(cookie, { allowPseudo }) ||
    localeFromAcceptLanguage(acceptLanguage) ||
    DEFAULT_LOCALE
  );
}
