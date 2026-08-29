"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { isDesktopShell } from "@/lib/shell";

export default function NotFound() {
  // In the shell there is no address bar and no history the user can reason
  // about, so "you typed it wrong" is the wrong story — a bad link inside the
  // app is. Sign-in is also not a place a signed-in desktop user should be
  // pointed back to.
  //
  // Resolved in an effect, not during render: `window.__TAURI__` does not exist
  // on the server, so reading it inline would make the first client render
  // disagree with the server's and trip a hydration mismatch. Starting false
  // means both agree, and the desktop wording swaps in a tick later.
  const [desktop, setDesktop] = useState(false);
  useEffect(() => setDesktop(isDesktopShell()), []);

  return (
    <main className="mx-auto flex min-h-[70vh] w-full max-w-2xl flex-col items-center justify-center px-6 py-12 text-center">
      <p className="mb-2 text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">
        404
      </p>
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        Page not found
      </h1>
      <p className="mt-3 max-w-md text-sm text-muted-foreground sm:text-base">
        {desktop
          ? "This screen doesn't exist or has moved. Nothing is wrong with your install."
          : "The page you are looking for does not exist or has moved."}
      </p>

      <div className="mt-7 flex w-full flex-col items-center justify-center gap-3 sm:flex-row">
        <Button asChild size="lg">
          <Link href="/insights/organic-growth">Go to Home</Link>
        </Button>
        {!desktop && (
          <Button asChild variant="outline" size="lg">
            <Link href="/">Go to Sign In</Link>
          </Button>
        )}
      </div>
    </main>
  );
}
