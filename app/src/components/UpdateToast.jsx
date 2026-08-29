"use client";

// Desktop update prompt.
//
// A toast rather than a modal or a forced restart: an update is never urgent
// enough to interrupt what someone is in the middle of, and this app's sessions
// are long — an agent run in flight would be lost to a surprise relaunch. So it
// waits in the corner until the user chooses, and a dismissal sticks for that
// version.
//
// Renders nothing at all in the browser, and nothing in shells without the
// `autoUpdate` capability (the Mac App Store build, where self-update is
// grounds for rejection) — see lib/updater.js.

import { useCallback, useEffect, useState } from "react";
import { ArrowUpCircle, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  INITIAL_DELAY_MS,
  RECHECK_INTERVAL_MS,
  checkForUpdate,
  dismiss,
  installUpdate,
  isDismissed,
} from "@/lib/updater";

export default function UpdateToast() {
  const [update, setUpdate] = useState(null);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    let interval;

    async function look() {
      const found = await checkForUpdate();
      if (!alive || !found || isDismissed(found.version)) return;
      setUpdate(found);
    }

    // Deliberately not on mount: the sidecar is still booting and the first
    // paint matters more than an update check that can wait 20 seconds.
    const timer = setTimeout(() => {
      look();
      interval = setInterval(look, RECHECK_INTERVAL_MS);
    }, INITIAL_DELAY_MS);

    return () => {
      alive = false;
      clearTimeout(timer);
      if (interval) clearInterval(interval);
    };
  }, []);

  const onInstall = useCallback(async () => {
    setInstalling(true);
    setError("");
    try {
      // On success the shell relaunches and this never resolves.
      await installUpdate();
    } catch (err) {
      setError(String(err?.message || err));
      setInstalling(false);
    }
  }, []);

  const onDismiss = useCallback(() => {
    if (update) dismiss(update.version);
    setUpdate(null);
  }, [update]);

  if (!update) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-border bg-background/95 p-4 shadow-lg ring-1 ring-border/40 backdrop-blur-xl"
    >
      <div className="flex items-start gap-3">
        <ArrowUpCircle className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">
            Duct {update.version} is available
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            You&rsquo;re on {update.currentVersion}. Updating restarts the app.
          </p>
          {update.notes ? (
            <p className="mt-2 line-clamp-3 text-xs text-muted-foreground">{update.notes}</p>
          ) : null}
          {error ? (
            <p className="mt-2 text-xs text-destructive">Update failed: {error}</p>
          ) : null}
          <div className="mt-3 flex items-center gap-2">
            <Button size="sm" onClick={onInstall} disabled={installing}>
              {installing ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" aria-hidden />
                  Installing…
                </>
              ) : (
                "Restart to update"
              )}
            </Button>
            <Button size="sm" variant="ghost" onClick={onDismiss} disabled={installing}>
              Later
            </Button>
          </div>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          disabled={installing}
          aria-label="Dismiss update notification"
          className="-mr-1 -mt-1 rounded p-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}
