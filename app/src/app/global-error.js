"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

import AppErrorPanel from "../components/AppErrorPanel";

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return <AppErrorPanel error={error} reset={reset} showHtmlShell />;
}
