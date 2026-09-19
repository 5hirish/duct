import { defineConfig } from "@lingui/cli";
import { formatter } from "@lingui/format-po";

/**
 * The four interface languages beside English, and a pseudo-locale.
 *
 * `es`, `pt-BR`, `de` and `ja` are the markets Duct is most likely to be
 * adopted in outside English *and* the largest non-English open-source
 * contributor bases; the two lists overlap almost exactly. Japanese is on it
 * instead of French because it is the large SaaS market with the lowest
 * English adoption. Adding a language is one entry here plus one line in
 * `src/i18n/locales.js`; the catalogue fills itself (see `scripts/i18n/`).
 *
 * `pseudo` is never shipped. It stretches every string and brackets it, so a
 * layout that clips German (~30% longer than English) shows up in /preview
 * without a German speaker in the room.
 */
export default defineConfig({
  sourceLocale: "en",
  locales: ["en", "es", "pt-BR", "de", "ja", "pseudo"],
  pseudoLocale: "pseudo",
  fallbackLocales: { pseudo: "en", default: "en" },
  catalogs: [
    {
      path: "<rootDir>/src/locales/{locale}/messages",
      include: ["<rootDir>/src"],
      exclude: ["**/node_modules/**", "**/__tests__/**", "**/__fixtures__/**"],
    },
  ],
  // Line numbers in `#:` references churn on every unrelated edit and turn a
  // one-string change into a hundred-line diff. File references alone are
  // enough to find a string.
  format: formatter({ lineNumbers: false }),
  compileNamespace: "es",
});
