"use client";

// Connection loss, said in the terms of whichever shell the user is in.
//
// A banner rather than a full-page takeover, on purpose: this fires *mid*
// session, and an agent run or an unsaved draft is usually in flight. Replacing
// the page would destroy work over a condition that is often transient. The
// full-page treatment belongs to boot-time failure, which LocalBackendGate
// already owns.
//
// The advice differs by platform in a way that is not cosmetic. On the web an
// unreachable API means Duct's servers; on desktop it means the backend running
// on this machine, and "check your internet" would be actively wrong — the
// sidecar is loopback, so it fails while the network is perfectly fine. The
// reverse is also true: a desktop user who is offline still has a working local
// backend, and only the model providers are out of reach.

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, WifiOff } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Button } from "@/components/ui/button";
import { STATUS, probe, watchConnection } from "@/lib/connection";
import { isLocalBackendActive } from "@/lib/localBackend";
import { isDesktopShell } from "@/lib/shell";

// Descriptors, not strings: this runs outside the component, where a `t`
// would be fixed in whatever language the module first loaded in.
function message(status, { desktop, localSidecar }) {
  if (status === STATUS.OFFLINE) {
    return desktop && localSidecar
      ? {
          title: msg`You're offline`,
          detail:
            msg`Duct's local backend is still running, so your saved work is fine. Agents need a connection to reach model providers.`,
        }
      : {
          title: msg`You're offline`,
          detail: msg`Duct needs a connection. Your work is saved and will still be here.`,
        };
  }
  if (localSidecar) {
    return {
      title: msg`Duct's local backend stopped responding`,
      detail:
        msg`The backend that runs inside the app is not answering. Quitting and reopening Duct restarts it.`,
    };
  }
  return desktop
    ? {
        title: msg`Can't reach Duct`,
        detail: msg`The app is online but Duct's servers are not responding. This is usually brief.`,
      }
    : {
        title: msg`Can't reach Duct`,
        detail: msg`Your connection is fine but Duct's servers are not responding. This is usually brief.`,
      };
}

export default function ConnectionBanner() {
  const { i18n } = useLingui();
  const [status, setStatus] = useState(STATUS.OK);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => watchConnection(setStatus), []);

  const retry = useCallback(async () => {
    setRetrying(true);
    setStatus(await probe());
    setRetrying(false);
  }, []);

  if (status === STATUS.OK) return null;

  const desktop = isDesktopShell();
  const localSidecar = isLocalBackendActive();
  const { title, detail } = message(status, { desktop, localSidecar });

  return (
    <div
      role="status"
      aria-live="polite"
      // A fixed bar with nothing reserved under it covered the last field of a
      // form at 375px and the sidebar's account row at 1024px — on the one
      // screen where the user is being told something has gone wrong and may
      // need to act on it. `--connection-banner-height` is read by the app
      // shell's scroll containers (app-shell.css) to pad exactly this much,
      // and only while the banner is mounted.
      data-connection-banner=""
      className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-background/95 px-4 py-3 shadow-lg backdrop-blur-xl sm:inset-x-auto sm:bottom-4 sm:left-4 sm:max-w-md sm:rounded-lg sm:border"
    >
      <div className="flex items-start gap-3">
        <WifiOff className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">{i18n._(title)}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{i18n._(detail)}</p>
        </div>
        <Button size="sm" variant="outline" onClick={retry} disabled={retrying}>
          <RefreshCw className={retrying ? "size-3.5 animate-spin" : "size-3.5"} aria-hidden />
          {retrying ? <Trans>Checking…</Trans> : <Trans>Retry</Trans>}
        </Button>
      </div>
    </div>
  );
}
