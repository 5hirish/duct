"use client";

// "Duct has been updated — reload to get it."
//
// The web counterpart to UpdateToast: same corner, same restraint, different
// mechanism. There is nothing to install, so the CTA is a reload and the whole
// component is a comparison of two strings.
//
// It renders nothing in a build with no baked id (local dev, any build that did
// not set NEXT_PUBLIC_BUILD_ID) and nothing in the desktop shell, where
// UpdateToast already owns this conversation and the app is not served from a
// worker anyone redeployed.

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CornerNotice } from "@/components/ui/corner-notice";
import {
  INITIAL_DELAY_MS,
  POLL_INTERVAL_MS,
  dismiss,
  fetchDeployedBuild,
  isDismissed,
  isStale,
  reload,
  versionCheckAvailable,
} from "@/lib/appVersion";
import { isDesktopShell } from "@/lib/shell";

export default function ReloadToast() {
  const [build, setBuild] = useState("");
  // The check runs on a timer and on focus; both can be in flight at once after
  // a laptop wakes. One at a time, and the loser is dropped rather than queued.
  const busy = useRef(false);

  useEffect(() => {
    if (!versionCheckAvailable()) return undefined;
    if (isDesktopShell()) return undefined;

    let alive = true;
    let interval;

    async function look() {
      if (busy.current || document.visibilityState === "hidden") return;
      busy.current = true;
      try {
        const deployed = await fetchDeployedBuild();
        if (!alive || !isStale(deployed) || isDismissed(deployed)) return;
        setBuild(deployed);
      } finally {
        busy.current = false;
      }
    }

    // Checking on focus is the case that actually matters. The tab left open
    // over a weekend is the stale one, and it is stale for hours before anyone
    // returns to it — a poll interval alone would either be uselessly slow or
    // wasteful for every tab that is simply being used.
    function onVisible() {
      if (document.visibilityState === "visible") look();
    }

    const timer = setTimeout(() => {
      look();
      interval = setInterval(look, POLL_INTERVAL_MS);
    }, INITIAL_DELAY_MS);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      alive = false;
      clearTimeout(timer);
      if (interval) clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const onDismiss = useCallback(() => {
    if (build) dismiss(build);
    setBuild("");
  }, [build]);

  if (!build) return null;

  return (
    <CornerNotice
      icon={RefreshCw}
      title="A new version of Duct is ready"
      onDismiss={onDismiss}
      dismissLabel="Dismiss update notification"
      actions={
        <>
          <Button size="sm" onClick={reload}>
            Reload
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Later
          </Button>
        </>
      }
    >
      {/* Say what reloading costs, because in this app it can cost something.
          "Refresh for the latest" would be true and would still get someone's
          half-written prompt thrown away. */}
      <p className="mt-0.5 text-xs text-muted-foreground">
        This tab is running an older build. Reloading picks up the new one — finish anything
        you have in progress first, it will not wait for you.
      </p>
    </CornerNotice>
  );
}
