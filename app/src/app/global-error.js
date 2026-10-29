"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";
import { i18n } from "@lingui/core";
import { I18nProvider } from "@lingui/react";

import AppErrorPanel from "../components/AppErrorPanel";

/**
 * The boundary for a root layout that threw, so it renders without the
 * layout's i18n provider, and the panel's own copy would throw a second time
 * on the missing catalogue. The global instance is whatever the provider had
 * activated before the failure; when it never got that far, English with no
 * catalogue still renders, where a second throw renders nothing at all.
 */
export default function GlobalError({ error, reset }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  if (!i18n.locale) i18n.loadAndActivate({ locale: "en", messages: {} });

  return (
    <I18nProvider i18n={i18n}>
      <AppErrorPanel error={error} reset={reset} showHtmlShell />
    </I18nProvider>
  );
}
