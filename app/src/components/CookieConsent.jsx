"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";

/**
 * The consent question, as a bar rather than a blocking overlay: the page stays
 * readable while it is open, and Decline sits at the same size and the same
 * click distance as Accept — the part the AEPD actually checks.
 *
 * Presentational only. `ProductAnalytics` owns the decision and the tags.
 */
export function CookieConsent({ onAccept, onDecline }) {
  const heading = useRef(null);

  // Move focus to the question when it appears, or a screen reader is never
  // told it is there — the same thing the site build does on `showBanner`.
  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <section
      role="dialog"
      aria-modal="false"
      aria-labelledby="consent-title"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-3xl flex-wrap items-center gap-6 rounded-xl border border-border bg-card p-5 shadow-lg"
    >
      <div className="min-w-0 flex-1 basis-80">
        <h2
          id="consent-title"
          ref={heading}
          tabIndex={-1}
          className="mb-1.5 text-sm font-semibold text-foreground outline-none"
        >
          Cookies, honestly
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          We use Google Analytics to see which pages earn a signup. That is the whole
          use — no ad targeting, no profiles, nothing sold. Decline and Duct behaves
          exactly the same.{" "}
          <a
            href="https://getduct.ai/privacy"
            target="_blank"
            rel="noreferrer noopener"
            className="text-foreground underline underline-offset-2"
          >
            Privacy Policy
          </a>
        </p>
      </div>
      <div className="flex w-full shrink-0 gap-2.5 sm:w-auto">
        <Button variant="outline" className="flex-1 sm:flex-none" onClick={onDecline}>
          Decline
        </Button>
        <Button className="flex-1 sm:flex-none" onClick={onAccept}>
          Accept
        </Button>
      </div>
    </section>
  );
}
