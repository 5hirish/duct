"use client";

/**
 * Holds the subtree's *hydration*, not its HTML, until the API base is known.
 *
 * The server renders the children as it would anywhere else, so the first
 * paint is the real page. This used to hold the HTML too: it rendered
 * "Starting Duct…" until an effect ran, and effects never run on the server,
 * so every route arrived as that one line and waited for all of its
 * JavaScript before showing anything. In a browser that wait bought nothing.
 *
 * In a browser the base is known on the first client render and the page
 * hydrates at once. In the desktop shell the children suspend during
 * hydration until the shell names its backend: React keeps the server's HTML
 * on screen and runs no effect or handler below this point until then. That
 * is the guarantee this gate exists for — nothing below fires a request at
 * the hosted API while the shell meant its bundled one, which the session
 * reads as a sign-out (see `lib/localBackend.js`).
 *
 * Wrap subtrees that talk to the API — not the root layout, whose children
 * include static marketing routes that need no backend at all.
 */

import { Suspense, use, useEffect } from "react";
import { Trans } from "@lingui/react/macro";

import { initLocalBackend, settledBackend } from "../lib/localBackend.js";
import { installExternalLinkHandler } from "../lib/shell.js";

export default function LocalBackendGate({ children }) {
  // Same subtrees, same shell: this is where the app's own chrome lives, so
  // it is where new-tab links have to be taught to reach the system browser.
  // Outside the boundary, so it is live while the children wait.
  useEffect(() => installExternalLinkHandler(), []);

  // The fallback shows only on a client navigation that beats the shell's
  // answer. During hydration React keeps the server's HTML instead.
  return (
    <Suspense fallback={<Starting />}>
      <Settled>{children}</Settled>
    </Suspense>
  );
}

function Settled({ children }) {
  // Settled during render, not in an effect: effects run children first, so
  // theirs would fire before ours.
  const backend = settledBackend() ?? use(initLocalBackend());
  // A terminal failure replaces the server's HTML, which React reports as a
  // hydration mismatch and recovers from. It only happens in a self-host
  // shell whose sidecar did not start.
  if (backend.error) return <BackendFailed detail={backend.error} />;
  return children;
}

function Starting() {
  return (
    <div className="flex min-h-svh items-center justify-center p-8">
      <p className="text-sm text-muted-foreground"><Trans>Starting Duct…</Trans></p>
    </div>
  );
}

function BackendFailed({ detail }) {
  return (
    <div className="flex min-h-svh items-center justify-center p-8">
      <div className="max-w-md space-y-2 text-center">
        <h1 className="text-lg font-semibold text-foreground">
          <Trans>Duct’s local backend didn’t start</Trans>
        </h1>
        <p className="text-sm text-muted-foreground">{detail}</p>
        <p className="text-sm text-muted-foreground">
          <Trans>
            Quit and reopen Duct. If it keeps happening, the app bundle may be
            incomplete — reinstall it.
          </Trans>
        </p>
      </div>
    </div>
  );
}
