"use client";

// The session with no model yet.
//
// Someone who skipped the provider step lands here instead of on a 402: the
// site is read, the project is drafted, and the one thing missing is a key.
// So the card says what is ready and offers the same provider control the
// step had, inline, where the first assistant turn would be. On success the
// caller mounts the real workspace and the audit starts.

import { useState } from "react";
import { Button } from "@/components/ui/button";
import ProviderStep from "./ProviderStep";

export default function ProviderRequiredCard({ siteUrl, pagesRead = 0, onConnected }) {
  const [open, setOpen] = useState(false);
  const host = (() => {
    try {
      return new URL(siteUrl).host;
    } catch {
      return siteUrl;
    }
  })();

  return (
    <div className="mx-auto w-full max-w-xl p-6">
      <div className="rounded-xl border bg-card p-6 shadow-sm">
        <h2 className="text-lg font-semibold tracking-tight">Ready when you are</h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          {pagesRead > 0 ? `I've read ${pagesRead} pages of ${host}` : `I've read ${host}`} and drafted your
          project from what I found. Connect a model and I'll start the audit.
        </p>
        {open ? (
          <ProviderStep
            className="mt-5"
            onVerified={(v) => {
              if (v?.ok === false) return;
              onConnected?.(v);
            }}
            onSkip={() => setOpen(false)}
          />
        ) : (
          <Button type="button" className="mt-5" onClick={() => setOpen(true)}>
            Connect a model
          </Button>
        )}
      </div>
    </div>
  );
}
