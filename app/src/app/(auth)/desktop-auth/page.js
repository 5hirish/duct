"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";

// Relay page for desktop sign-in. After Google OAuth completes in the user's
// browser, the backend redirects here with a one-time auth code; this page
// hands the code to the desktop shell via its custom URL scheme and tells the
// user to head back to the app. It must never call /auth/exchange itself —
// the code is single-use and belongs to the shell's webview.
//
// It is also where the backend sends *failed* sign-ins (`?error=`). The OAuth
// dance runs in the system browser, so anything the loopback sidecar returns is
// rendered raw: without this the user lands on `{"detail": ...}` or a bare
// "Internal Server Error" after already approving at Google. See
// `_signin_failure` in `backend/routes/signin.py`.
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

function DesktopAuthContent() {
  const searchParams = useSearchParams();
  const [deepLink, setDeepLink] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    const reason = searchParams.get("error") || "";
    if (reason) {
      setError(ERRORS[reason] || FALLBACK);
      return;
    }
    const authCode = searchParams.get("auth_code") || "";
    if (!authCode) {
      setError(ERRORS.expired);
      return;
    }
    // Scrub the one-time code from the address bar and history, then fire the
    // deep link that returns it to the shell.
    window.history.replaceState({}, "", "/desktop-auth");
    const link = `${SHELL_SCHEME}://auth?auth_code=${encodeURIComponent(authCode)}`;
    setDeepLink(link);
    window.location.href = link;
  }, [searchParams]);

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
              You&rsquo;re signed in
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
