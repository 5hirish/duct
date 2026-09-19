/**
 * The request's language, on the server.
 *
 * Server components have no React context, so Lingui keeps one `I18n` per
 * request behind React's `cache`. Every server component that renders copy
 * goes through `activateRequestI18n()` first — the root layout does, and so
 * must any server page or layout that renders translatable text, because on a
 * client-side navigation Next renders the page without its parent layouts.
 *
 * Every catalogue is imported statically. Five compiled catalogues is well
 * under a megabyte and the Worker holds them once; a dynamic import per
 * request would spend a cold start to save memory nobody was short of.
 */
import { cache } from "react";
import { setupI18n } from "@lingui/core";
import { setI18n } from "@lingui/react/server";
import { cookies, headers } from "next/headers";

import { messages as en } from "../locales/en/messages.mjs";
import { messages as es } from "../locales/es/messages.mjs";
import { messages as ptBR } from "../locales/pt-BR/messages.mjs";
import { messages as de } from "../locales/de/messages.mjs";
import { messages as ja } from "../locales/ja/messages.mjs";
import { messages as pseudo } from "../locales/pseudo/messages.mjs";

import { LOCALE_COOKIE, PSEUDO_LOCALE, resolveLocale } from "./locales";

const CATALOGS = { en, es, "pt-BR": ptBR, de, ja, [PSEUDO_LOCALE]: pseudo };

/** One instance per request and locale. */
export const getI18nInstance = cache((locale) => {
  const messages = CATALOGS[locale] || CATALOGS.en;
  return setupI18n({ locale, messages: { [locale]: messages } });
});

/**
 * Cookie, then Accept-Language, then English.
 *
 * The pseudo-locale is only reachable outside production: it exists to stretch
 * layouts in /preview, and a production request that somehow carried it would
 * render bracketed gibberish to a real person.
 */
export async function requestLocale() {
  const jar = await cookies();
  const requestHeaders = await headers();
  return resolveLocale({
    cookie: jar.get(LOCALE_COOKIE)?.value,
    acceptLanguage: requestHeaders.get("accept-language"),
    allowPseudo: process.env.NODE_ENV !== "production",
  });
}

/** Resolve the locale and make its catalogue current for this request. */
export async function activateRequestI18n() {
  const locale = await requestLocale();
  const i18n = getI18nInstance(locale);
  setI18n(i18n);
  return i18n;
}
