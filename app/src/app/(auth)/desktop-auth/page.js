"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";

// Relay page for desktop sign-in. After Google OAuth completes in the user's
// browser, the backend redirects here with a one-time auth code; this page
// hands the code to the desktop shell via its custom URL scheme and tells the
// user to head back to the app. It must never call /auth/exchange itself —
// the code is single-use and belongs to the shell's webview.
const SHELL_SCHEME = "ai.getduct.desktop";

function DesktopAuthContent() {
  const searchParams = useSearchParams();
  const [deepLink, setDeepLink] = useState("");
  const [missingCode, setMissingCode] = useState(false);

  useEffect(() => {
    const authCode = searchParams.get("auth_code") || "";
    if (!authCode) {
      setMissingCode(true);
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
        {missingCode ? (
          <>
            <h1 id="desktop-auth-heading" className="text-xl font-semibold">
              Sign-in link expired
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              This link is missing its sign-in code. Go back to the Duct
              desktop app and sign in again.
            </p>
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
