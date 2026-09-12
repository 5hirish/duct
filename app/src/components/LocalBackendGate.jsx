"use client";

/**
 * Holds rendering until the API base URL is known.
 *
 * In the browser this resolves on the first tick and is effectively invisible.
 * In the desktop shell it waits for the bundled backend to finish booting and
 * report its loopback port, because anything that renders sooner would fire its
 * requests at the hosted API instead of the local one.
 *
 * Wrap subtrees that talk to the API — not the root layout, whose children
 * include static marketing routes that need no backend at all.
 */

import { useEffect, useState } from "react";

import { reconcileStoredSession } from "../lib/authFetch.js";
import { initLocalBackend } from "../lib/localBackend.js";
import { installExternalLinkHandler } from "../lib/shell.js";

export default function LocalBackendGate({ children }) {
  // Starts false on both server and client so the first paint matches; the
  // effect below flips it once the backend is resolved.
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    initLocalBackend().then((result) => {
      if (!alive) return;
      if (result.error) {
        // The base never moved, so it does not describe the backend this shell
        // meant to use. Judging the stored session against it would throw away
        // a session that is still good for the sidecar that failed to start.
        setError(result.error);
      } else {
        reconcileStoredSession();
      }
      setReady(true);
    });
    // Same subtrees, same shell: this is where the app's own chrome lives, so
    // it is where new-tab links have to be taught to reach the system browser.
    const uninstall = installExternalLinkHandler();
    return () => {
      alive = false;
      uninstall();
    };
  }, []);

  if (error) {
    return (
      <div className="flex min-h-svh items-center justify-center p-8">
        <div className="max-w-md space-y-2 text-center">
          <h1 className="text-lg font-semibold text-foreground">
            Duct&rsquo;s local backend didn&rsquo;t start
          </h1>
          <p className="text-sm text-muted-foreground">{error}</p>
          <p className="text-sm text-muted-foreground">
            Quit and reopen Duct. If it keeps happening, the app bundle may be
            incomplete — reinstall it.
          </p>
        </div>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="flex min-h-svh items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Starting Duct…</p>
      </div>
    );
  }

  return children;
}
