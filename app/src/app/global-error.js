"use client";

import { useEffect } from "react";

import AppErrorPanel from "../components/AppErrorPanel";
import { reportError } from "../lib/analytics";

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    reportError(error, { boundary: "global" });
  }, [error]);

  return <AppErrorPanel error={error} reset={reset} showHtmlShell />;
}
