"use client";

import AppErrorPanel from "../components/AppErrorPanel";

export default function Error({ error, reset }) {
  return <AppErrorPanel error={error} reset={reset} />;
}
