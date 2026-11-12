"use client";

import { useEffect, useState } from "react";
import { PROJECTS_CHANGED, getActiveProjectId } from "@/lib/projects";
import { waitingCount } from "@/lib/schedules";
import { listSchedules } from "@/lib/schedulesApi";

/**
 * How many of the active project's schedules have a proposal waiting on the
 * person (#563): the sidebar's count beside Scheduled. A run happens while
 * nobody is looking, so this is how anyone hears that it left something.
 *
 * Asked on mount, on a project switch, when the window regains focus (a run
 * that finished while the tab was in the background) and when the route
 * changes (`key`, so leaving the Scheduled page after an Accept clears it).
 * Never polled: a count nobody can see costs a request for nothing.
 */
export function useScheduledWaiting(key) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    const check = () => {
      const projectId = getActiveProjectId();
      if (!projectId) {
        setCount(0);
        return;
      }
      listSchedules(projectId)
        .then((rows) => { if (alive) setCount(waitingCount(rows)); })
        .catch(() => { if (alive) setCount(0); });
    };
    check();
    window.addEventListener(PROJECTS_CHANGED, check);
    window.addEventListener("focus", check);
    return () => {
      alive = false;
      window.removeEventListener(PROJECTS_CHANGED, check);
      window.removeEventListener("focus", check);
    };
  }, [key]);
  return count;
}
