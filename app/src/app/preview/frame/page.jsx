import { notFound } from "next/navigation";
import { setI18n } from "@lingui/react/server";
import { LinguiClientProvider } from "../../../i18n/LinguiClientProvider";
import { getI18nInstance } from "../../../i18n/server";
import { DEFAULT_LOCALE, normalizeLocale } from "../../../i18n/locales";

// One scene, alone in its own document.
//
// This is the route that matters for an agent: everything is in the URL, so a
// state is addressable without clicking anything —
//   /preview/frame?scene=tile-states&surface=dialog&theme=dark&inspect=outline
// Point a browser at it with the viewport set to the device you care about and
// the answer is on screen with no shell chrome in the way.
//
// The shell at /preview embeds these in iframes, which is the only honest way
// to show several devices at once: media queries read the viewport, and a
// resized <div> is not one.
//
// The language is `?lang=` and nothing else — English when absent. The root
// layout resolves the app's language from the `duct_lang` cookie and then
// the browser's Accept-Language, which is right for the app and wrong for a
// harness: a developer in Spain opened /preview and every scene came up in
// Spanish, and the shell's language picker used to write that same cookie,
// so switching a scene to Japanese switched the app too. The frame now
// overrides the layout's provider for its own subtree with the language in
// its URL, and the picker writes nothing but the URL.
export const metadata = { robots: { index: false, follow: false } };

export default async function PreviewFramePage({ searchParams }) {
  if (process.env.NODE_ENV === "production") notFound();
  const { lang } = await searchParams;
  const locale = normalizeLocale(lang, { allowPseudo: true }) || DEFAULT_LOCALE;
  const i18n = getI18nInstance(locale);
  setI18n(i18n);
  const { default: PreviewFrame } = await import("../PreviewFrame");
  return (
    <LinguiClientProvider initialLocale={locale} initialMessages={i18n.messages}>
      <PreviewFrame />
    </LinguiClientProvider>
  );
}
