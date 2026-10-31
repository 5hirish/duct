"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getActiveProjectId, PROJECTS_CHANGED } from "@/lib/projects";

/**
 * The active project's id, kept current. The sidebar switcher and ⌘K change it
 * without a navigation, so a page that reads getActiveProjectId() once on
 * mount keeps showing the previous project until a reload — which is what
 * Content Studio did. `null` until mounted (the pick lives in browser
 * storage), "" when no project is picked.
 */
export function useActiveProjectId() {
  const [id, setId] = useState(null);
  useEffect(() => {
    const sync = () => setId(getActiveProjectId() || "");
    sync();
    window.addEventListener(PROJECTS_CHANGED, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(PROJECTS_CHANGED, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return id;
}

/**
 * True once the active project differs from the one this page opened with.
 * Compared against the opening pick rather than the page's own project, so a
 * link into another project's post still opens it; only a switch made while
 * the page is up counts.
 */
export function useProjectSwitched() {
  const activeId = useActiveProjectId();
  const [openedWith, setOpenedWith] = useState(null);
  if (activeId !== null && openedWith === null) setOpenedWith(activeId);
  return openedWith !== null && activeId !== openedWith;
}

/**
 * Leave for `href` when the project is switched under a page that belongs to
 * one project: a post, or a chat already running for the old project, which
 * would otherwise keep writing there while the sidebar names the new one.
 */
export function useLeaveOnProjectSwitch(href = "/content") {
  const router = useRouter();
  const switched = useProjectSwitched();
  useEffect(() => {
    if (switched) router.replace(href);
  }, [switched, href, router]);
}
