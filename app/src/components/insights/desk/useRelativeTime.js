"use client";

// "18 minutes ago", in the interface language, for the desk's three surfaces.
//
// lib/desk.js formats the interval through Intl and has no word for the one
// case Intl lacks — under a minute — so it hands back "" and the component
// says "just now" through Lingui. A row with no timestamp at all stays blank
// rather than claiming it.

import { useLingui } from "@lingui/react/macro";
import { relativeTime } from "@/lib/desk";

/** Returns `(iso) => string`; `""` when there is no timestamp to speak of. */
export function useRelativeTime() {
  const { t, i18n } = useLingui();
  return (at) => (at ? relativeTime(at, { locale: i18n.locale }) || t`just now` : "");
}
