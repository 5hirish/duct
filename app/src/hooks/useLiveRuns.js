"use client";

/**
 * The runs this tab left behind, kept honest.
 *
 * lib/liveRuns.js knows when a page detached from a run; nothing in this tab
 * hears the run finish, because the page that was listening is gone. So while
 * any run is noted, this polls its session state and drops the entry once the
 * backend says the turn is over, or the session itself is gone (closed after
 * its grace, or stopped from another tab). A backend too old to report
 * `running` leaves the entry until the page reattaches.
 */

import { useEffect, useSyncExternalStore } from "react";

import { getAgentSessionState } from "../lib/api";
import { forgetDetachedRun, listDetachedRuns, subscribeDetachedRuns } from "../lib/liveRuns";

const LIVE_RUN_POLL_MS = 15_000;
const NONE = Object.freeze([]);

export function useLiveRuns() {
  const runs = useSyncExternalStore(subscribeDetachedRuns, listDetachedRuns, () => NONE);

  useEffect(() => {
    if (!runs.length) return undefined;
    let cancelled = false;

    async function settle() {
      for (const run of runs) {
        try {
          const state = await getAgentSessionState(run.agentType, run.sessionId);
          if (!cancelled && state?.running === false) forgetDetachedRun(run.sessionId);
        } catch {
          if (!cancelled) forgetDetachedRun(run.sessionId);
        }
      }
    }

    const timer = setInterval(settle, LIVE_RUN_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [runs]);

  return runs;
}
