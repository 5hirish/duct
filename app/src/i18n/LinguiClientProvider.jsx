"use client";

import { useEffect, useState } from "react";
import { i18n as globalI18n, setupI18n } from "@lingui/core";
import { I18nProvider } from "@lingui/react";

/**
 * Hands the server's `I18n` to client components, by value.
 *
 * The instance itself is not serialisable, so the layout passes the locale
 * and the compiled messages and this rebuilds one on the client. When the
 * locale changes (a profile save followed by `router.refresh()`), the layout
 * re-renders with new props and the effect swaps the catalogue in place,
 * which is what lets every mounted component re-render in the new language
 * without a full reload.
 *
 * The global `i18n` from @lingui/core is kept in step too. `<Trans>` and
 * `useLingui()` read the context instance, but the `plural()` and `select()`
 * macros compile to a call on the global one, and a plural that renders in
 * English inside an otherwise Spanish page is exactly the bug nobody would
 * find until a Spanish speaker did.
 */
export function LinguiClientProvider({ children, initialLocale, initialMessages }) {
  const [i18n] = useState(() => {
    globalI18n.loadAndActivate({ locale: initialLocale, messages: initialMessages });
    return setupI18n({ locale: initialLocale, messages: { [initialLocale]: initialMessages } });
  });

  useEffect(() => {
    if (i18n.locale !== initialLocale) {
      i18n.loadAndActivate({ locale: initialLocale, messages: initialMessages });
      globalI18n.loadAndActivate({ locale: initialLocale, messages: initialMessages });
    }
  }, [i18n, initialLocale, initialMessages]);

  return <I18nProvider i18n={i18n}>{children}</I18nProvider>;
}
