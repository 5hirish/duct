"use client";

// What a panel shows when its data did not arrive.
//
// Deliberately not the empty state. "No proposed changes yet — run an audit and
// recommended fixes land here" is an invitation to use the product; printing a
// server error in its place tells a new user their account is broken when in
// fact one request failed. The two are mutually exclusive, and the reason is
// not cosmetic: a panel that never heard back does not know whether it is
// empty, so it has no standing to say so.
//
// This is not AppErrorPanel, which takes over the whole page when React itself
// throws. This one sits inside a page that otherwise works.
//
// `detail` is the backend's own words — never the only thing on screen,
// because it was written for us and not for the reader.

import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * @param what    Noun phrase completing "We couldn't load …" ("your artifacts").
 * @param detail  Server-supplied detail, shown as secondary text when present.
 * @param onRetry Optional; renders a retry button when given.
 */
export default function LoadError({ what, detail, onRetry }) {
  // The box is DESIGN.md's canon for a section-level failure — the tinted
  // destructive variant, not a neutral card and not a bare red line.
  return (
    <div
      role="alert"
      className="mt-4 mb-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3.5"
    >
      <p className="text-sm font-medium text-foreground">We couldn&rsquo;t load {what}.</p>
      <p className="mt-1 text-sm text-muted-foreground">
        This is usually temporary — try again in a moment.
      </p>
      {/* On its own line, not spliced into the sentence above: the backend's
          detail is a fragment ("User not found"), and reading it as the tail of
          our prose makes our copy sound broken as well. */}
      {detail && (
        <p className="mt-1.5 font-mono text-xs text-muted-foreground">{detail}</p>
      )}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden="true" /> Try again
        </Button>
      )}
    </div>
  );
}
