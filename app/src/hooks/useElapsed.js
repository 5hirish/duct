"use client";

import { useEffect, useState } from "react";

/**
 * Seconds since `active` last became true; 0 while it is false.
 *
 * A clock is what tells a person a four-minute run is alive, and it is the
 * one figure about a run's length the client can state without guessing: it
 * counts from when this component saw the work start, so a tab that
 * reattaches to a run mid-way shows the time since it rejoined, never an
 * estimate of the whole. The chat header's status row and the working panel
 * in the viewport both tick off this hook, so the two panes cannot disagree.
 */
export function useElapsed(active) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return undefined;
    }
    const startedAt = Date.now();
    setSeconds(0);
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return seconds;
}

export default useElapsed;
