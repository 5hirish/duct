"use client";

import { useEffect } from "react";

import AppErrorPanel from "../components/AppErrorPanel";
import { reportError } from "../lib/analytics";

/**
 * Route-level error boundary.
 *
 * The report is load-bearing, not boilerplate. React error boundaries swallow
 * what they catch, so a page failure that lands here never reaches the global
 * handlers that report uncaught errors. Most real crashes land here, and the
 * boundary that only fires when the root layout itself throws is the rare one.
 */
export default function Error({ error, reset }) {
  useEffect(() => {
    reportError(error, { boundary: "route" });
  }, [error]);

  return <AppErrorPanel error={error} reset={reset} />;
}
