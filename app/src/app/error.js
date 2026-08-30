"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

import AppErrorPanel from "../components/AppErrorPanel";

/**
 * Route-level error boundary.
 *
 * The `captureException` is load-bearing, not boilerplate. Sentry's Next.js SDK
 * does not auto-instrument React error boundaries — `global-error.js` had the
 * call and this did not, which meant the boundary that catches *ordinary* page
 * failures reported nothing, while the one that only fires when the root layout
 * itself throws reported everything. Most real crashes land here.
 */
export default function Error({ error, reset }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return <AppErrorPanel error={error} reset={reset} />;
}
