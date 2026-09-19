"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
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

// Keyed by the reason codes in `backend/routes/signin.py`. The title says what
// happened; the body is one sentence of what to do about it — "try again" is
// useless advice when the install is misconfigured, and alarming when the user
// simply took too long. Anything a bug report needs is in the Copy details
// button, not in the prose: this page cannot read the app's version, which is
// why three bodies used to send the reader to the About screen to transcribe
// one by hand.
const ERRORS = {
  expired: {
    title: msg`Sign-in link expired`,
    body: msg`Go back to the Duct desktop app and start again — it usually works second time.`,
    retryable: true,
  },
  exchange: {
    title: msg`Google didn't complete the sign-in`,
    body: msg`Google declined the exchange, which is almost always temporary. Try again from the app.`,
    retryable: true,
  },
  identity: {
    title: msg`Couldn't read your Google account`,
    body: msg`Google signed you in but sent no account details. Try again, or use a different Google account.`,
    retryable: true,
  },
  config: {
    title: msg`Sign-in isn't configured`,
    body: msg`Trying again won't help — this build shipped without its Google sign-in credentials.`,
    retryable: false,
  },
  server: {
    title: msg`Something broke on our side`,
    body: msg`It's logged on our side. Try again, and send us the details below if it keeps happening.`,
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
    title: msg`Connection link expired`,
    body: msg`Go back to the Duct desktop app and start the connection again.`,
    retryable: true,
  },
  exchange: {
    title: msg`Google didn't complete the connection`,
    body: msg`Google declined the exchange, which is almost always temporary. Try again from the app.`,
    retryable: true,
  },
  consent: {
    title: msg`Google didn't grant lasting access`,
    body: msg`Google sent no refresh token, which happens when you've approved Duct before. Try again and approve the access screen.`,
    retryable: true,
  },
  config: {
    title: msg`This connector isn't configured`,
    body: msg`Trying again won't help — this build shipped without that connector's credentials.`,
    retryable: false,
  },
  unknown: {
    title: msg`Unknown connector`,
    body: msg`Trying again won't help — Duct doesn't recognise the connector this link names.`,
    retryable: false,
  },
  server: {
    title: msg`Something broke on our side`,
    body: msg`It's logged on our side. Try again, and send us the details below if it keeps happening.`,
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
  const { t, i18n } = useLingui();
  const [deepLink, setDeepLink] = useState("");
  const [error, setError] = useState(null);
  const [connectorName, setConnectorName] = useState("");
  const [isConnector, setIsConnector] = useState(false);
  const [reason, setReason] = useState("");
  const [copied, setCopied] = useState(false);
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
      setReason(reason);
      return;
    }
    const authCode = searchParams.get("auth_code") || "";
    if (!authCode) {
      setError(isConnectorFlow ? CONNECTOR_ERRORS.expired : ERRORS.expired);
      setReason("expired");
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
  // Everything this page can honestly report. Not the app version — a browser
  // tab opened by the shell has no way to read it, which is the reason the old
  // copy asked the reader to go and find it themselves.
  const diagnostics = [
    `reason: ${reason || "unknown"}`,
    `flow: ${isConnector ? "connector" : "sign-in"}`,
    connectorName ? `connector: ${connectorName}` : "",
    `at: ${new Date().toISOString()}`,
  ]
    .filter(Boolean)
    .join(" · ");

  const successTitle = connectorName
    ? t`${connectorName} connected`
    : isConnector
      ? t`Connected`
      : t`You’re signed in`;

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
              {i18n._(error.title)}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">{i18n._(error.body)}</p>
            {/* What a bug report actually needs, as one click. The reason code
                is the field that makes a report diagnosable, and no reader was
                ever going to type it out of a paragraph. */}
            <Button
              variant="outline"
              size="sm"
              className="mt-5"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(diagnostics);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                } catch {
                  /* clipboard blocked — the details stay visible below */
                }
              }}
            >
              {copied ? <Trans>Copied</Trans> : <Trans>Copy details</Trans>}
            </Button>
            <p className="mt-3 font-mono text-2xs leading-relaxed text-muted-foreground">
              {diagnostics}
            </p>
            <p className="mt-4 text-xs text-muted-foreground">
              <Trans>You can close this tab.</Trans>
            </p>
          </>
        ) : (
          <>
            <h1 id="desktop-auth-heading" className="text-xl font-semibold">
              {successTitle}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              <Trans>Duct should open automatically. If it doesn&rsquo;t, use the button below.</Trans>
            </p>
            {deepLink && (
              <Button asChild size="lg" className="mt-6">
                <a href={deepLink}>
                  <Trans>Open Duct</Trans>
                </a>
              </Button>
            )}
            <p className="mt-4 text-xs text-muted-foreground">
              <Trans>You can close this tab.</Trans>
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
