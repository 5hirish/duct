"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";

// Relay page for the desktop app's two browser-based OAuth flows: signing in to
// Duct, and connecting a data source. Both run in the user's own browser —
// Google refuses OAuth inside an embedded webview — so both need a way back
// into the app. The backend redirects here with a one-time code; this page
// hands it to the desktop shell via its custom URL scheme and tells the user to
// head back to the app.
//
// It must never redeem a code itself: they are single-use and belong to the
// shell's webview (`/auth/exchange` for sign-in, `/auth/connectors/exchange`
// for a connector).
//
// It is also where the backend sends *failed* attempts (`?error=`). The OAuth
// dance runs in the system browser, so anything the loopback sidecar returns is
// rendered raw: without this the user lands on `{"detail": ...}` or a bare
// "Internal Server Error" after already approving at Google. See
// `_signin_failure` in `backend/routes/signin.py` and `_connector_failure` in
// `backend/routes/auth.py`.
//
// The scheme is build-time config, not user input: a local dev shell built from
// `src-tauri/tauri.dev.conf.json` registers `ai.getduct.desktop.dev` so it can
// coexist with an installed TestFlight build. Set NEXT_PUBLIC_SHELL_SCHEME in
// `app/.env.local` to match; deployed builds leave it unset.
const SHELL_SCHEME =
  process.env.NEXT_PUBLIC_SHELL_SCHEME?.trim() || "ai.getduct.desktop";

// Keyed by the reason codes in `backend/routes/signin.py`. Each one says what
// happened and what to do about it — "try again" is useless advice when the
// install is misconfigured, and alarming when the user simply took too long.
const ERRORS = {
  expired: {
    title: "Sign-in link expired",
    body: "This sign-in didn't complete in time. Go back to the Duct desktop app and start again — it usually works on the second try.",
    retryable: true,
  },
  exchange: {
    title: "Google didn't complete the sign-in",
    body: "Google declined to finish the exchange. This is almost always temporary. Go back to the Duct desktop app and try again.",
    retryable: true,
  },
  identity: {
    title: "Couldn't read your Google account",
    body: "Google signed you in but didn't return the account details Duct needs. Try again, and if it keeps happening, try a different Google account.",
    retryable: true,
  },
  config: {
    title: "Sign-in isn't configured",
    body: "This build of Duct is missing its Google sign-in credentials, so it can't sign anyone in. Trying again won't help — please report this with the version number from the app's About screen.",
    retryable: false,
  },
  server: {
    title: "Something broke on our side",
    body: "Duct hit an unexpected error finishing your sign-in. The details were written to the app's log. Try again, and if it keeps happening, please report it.",
    retryable: true,
  },
};

const FALLBACK = ERRORS.server;

// Same job for the connector flow, keyed by the reason codes in
// `backend/routes/auth.py`. Separate copy rather than shared strings: "sign-in
// expired" is the wrong sentence when what failed was connecting Google Ads,
// and `consent` has no sign-in equivalent at all.
const CONNECTOR_ERRORS = {
  expired: {
    title: "Connection link expired",
    body: "This didn't finish in time. Go back to the Duct desktop app and start the connection again.",
    retryable: true,
  },
  exchange: {
    title: "Google didn't complete the connection",
    body: "Google declined to finish the exchange. This is almost always temporary — go back to the Duct desktop app and try again.",
    retryable: true,
  },
  consent: {
    title: "Google didn't grant lasting access",
    body: "Google returned no refresh token, which happens when the account has already approved Duct before. Go back to the app, try again, and approve the access screen when it appears.",
    retryable: true,
  },
  config: {
    title: "This connector isn't configured",
    body: "This build of Duct is missing the credentials for that connector. Trying again won't help — please report this with the version number from the app's About screen.",
    retryable: false,
  },
  unknown: {
    title: "Unknown connector",
    body: "Duct doesn't recognise the connector this link was for. Please report this with the version number from the app's About screen.",
    retryable: false,
  },
  server: {
    title: "Something broke on our side",
    body: "Duct hit an unexpected error finishing the connection. The details were written to the app's log. Try again, and if it keeps happening, please report it.",
    retryable: true,
  },
};

// Only for display. An unrecognised id falls back to the generic wording rather
// than being echoed back into the page.
const CONNECTOR_NAMES = {
  google_ads: "Google Ads",
  ga4: "Google Analytics",
  gsc: "Google Search Console",
  gtm: "Google Tag Manager",
};

function DesktopAuthContent() {
  const searchParams = useSearchParams();
  const [deepLink, setDeepLink] = useState("");
  const [error, setError] = useState(null);
  const [connectorName, setConnectorName] = useState("");
  const [isConnector, setIsConnector] = useState(false);
  // The handover happens exactly once, and everything it needs is latched into
  // state below. Without this guard the scrub further down re-runs the effect:
  // Next keeps `useSearchParams` in sync with `history.replaceState`, so the
  // second pass sees the emptied query, reads it as a link that arrived with no
  // code, and replaces the success page with "Sign-in link expired" a beat
  // after the deep link has already fired — telling the user a connection
  // failed that in fact succeeded.
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    // `connector` present means this is a data-source connection coming home,
    // not a sign-in: a different deep-link route, and different copy. Present
    // and *empty* still means connector: the short-path callback in
    // `backend/routes/auth.py` fails with `connector=&error=expired` when the
    // state it would have named the connector from is the very thing that
    // expired, and "Sign-in link expired" is the wrong sentence for that.
    const connector = searchParams.get("connector") || "";
    const isConnectorFlow = searchParams.has("connector");
    setIsConnector(isConnectorFlow);
    setConnectorName(CONNECTOR_NAMES[connector] || "");

    const reason = searchParams.get("error") || "";
    if (reason) {
      const table = isConnectorFlow ? CONNECTOR_ERRORS : ERRORS;
      setError(table[reason] || table.server || FALLBACK);
      return;
    }
    const authCode = searchParams.get("auth_code") || "";
    if (!authCode) {
      setError(isConnectorFlow ? CONNECTOR_ERRORS.expired : ERRORS.expired);
      return;
    }
    // Scrub the one-time code from the address bar and history, then fire the
    // deep link that returns it to the shell.
    window.history.replaceState({}, "", "/desktop-auth");
    const link = isConnectorFlow
      ? `${SHELL_SCHEME}://connector?connector=${encodeURIComponent(connector)}` +
        `&auth_code=${encodeURIComponent(authCode)}`
      : `${SHELL_SCHEME}://auth?auth_code=${encodeURIComponent(authCode)}`;
    setDeepLink(link);
    window.location.href = link;
  }, [searchParams]);

  // Read from state, not the query: by the time this renders the code — and
  // the `connector` beside it — has been scrubbed out of the address bar.
  const successTitle = connectorName
    ? `${connectorName} connected`
    : isConnector
      ? "Connected"
      : "You’re signed in";

  return (
    <main
      id="main-content"
      className="flex min-h-dvh items-center justify-center bg-background px-6"
      aria-labelledby="desktop-auth-heading"
      tabIndex={-1}
    >
      <div className="w-full max-w-sm text-center">
        {error ? (
          <>
            <h1 id="desktop-auth-heading" className="text-xl font-semibold">
              {error.title}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">{error.body}</p>
            {error.retryable && (
              <p className="mt-4 text-xs text-muted-foreground">
                You can close this tab.
              </p>
            )}
          </>
        ) : (
          <>
            <h1 id="desktop-auth-heading" className="text-xl font-semibold">
              {successTitle}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Return to the Duct desktop app to continue — it should open
              automatically. If nothing happens, use the button below.
            </p>
            {deepLink && (
              <Button asChild size="lg" className="mt-6">
                <a href={deepLink}>Open Duct</a>
              </Button>
            )}
            <p className="mt-4 text-xs text-muted-foreground">
              You can close this tab.
            </p>
          </>
        )}
      </div>
    </main>
  );
}

export default function DesktopAuthPage() {
  return (
    <Suspense fallback={null}>
      <DesktopAuthContent />
    </Suspense>
  );
}
