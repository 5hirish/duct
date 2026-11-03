"use client";

import { useEffect, useState } from "react";
import { useLingui } from "@lingui/react/macro";
import { useAuthUser } from "@/lib/auth";

/**
 * "Good morning, Maya": the home screen's first line. The hour is this
 * device's, so it is read after mount; a server render does not know where the
 * reader is, and guessing would be a hydration mismatch and sometimes a wrong
 * "good evening" at breakfast. Empty until then, which the header simply skips.
 */
export function useGreeting() {
  const { t } = useLingui();
  const user = useAuthUser();
  const [hour, setHour] = useState(null);

  useEffect(() => {
    setHour(new Date().getHours());
  }, []);

  if (hour === null) return "";
  const name = (user?.name || "").trim().split(/\s+/)[0];
  if (hour < 5 || hour >= 18) return name ? t`Good evening, ${name}` : t`Good evening`;
  if (hour < 12) return name ? t`Good morning, ${name}` : t`Good morning`;
  return name ? t`Good afternoon, ${name}` : t`Good afternoon`;
}
