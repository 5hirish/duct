"use client";

import AppErrorPanel from "../components/AppErrorPanel";

export default function GlobalError({ error, reset }) {
  return <AppErrorPanel error={error} reset={reset} showHtmlShell />;
}
