"use client";

// The agent has decided it needs a data source this project has not connected,
// and has paused to ask. Rendered inline in the transcript, not as a modal:
// the reason it gives is part of the conversation, and a modal would imply the
// run is blocked on the user rather than politely waiting.
//
// Declining is a real button, not a dismissal. The agent is told the user
// skipped, continues with what it has, and says in its output what that left
// unverified — so "Skip" has to look like a choice, not an escape.

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { BASE } from "../../lib/api";
import { startConnectorOAuth } from "../../lib/connectorAuth";

export default function ConnectionRequest({ request, onAnswer, disabled }) {
  // "" | "starting" | "browser" — "browser" is the desktop shell waiting on the
  // system browser, where this window never navigates and the state is the only
  // thing telling the user anything happened. Mirrors OAuthConnectorCard.
  const [phase, setPhase] = useState("");

  const { connector_id: connectorId, label, reason, auth_kind: authKind, authorize_path: authorizePath } = request;
  const isManual = authKind === "manual" || !authorizePath;

  async function connect() {
    if (phase === "starting") return;
    setPhase("starting");
    try {
      const mode = await startConnectorOAuth(`${BASE}${authorizePath}`);
      setPhase(mode === "browser" ? "browser" : "starting");
    } catch {
      setPhase("");
    }
  }

  return (
    <div className="my-3 space-y-3 rounded-xl border border-sky-200 bg-sky-50/60 p-4 dark:border-sky-800/60 dark:bg-sky-950/20">
      <div className="space-y-0.5">
        <p className="text-sm font-semibold">Connect {label}?</p>
        {reason && <p className="text-xs text-muted-foreground">{reason}</p>}
      </div>

      {isManual ? (
        <p className="text-xs text-muted-foreground">
          {label} needs an API key rather than a sign-in. Add it on the{" "}
          <a href="/connections" className="underline underline-offset-2 hover:text-foreground">
            Connections page
          </a>
          , then tell Duct to carry on.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {!isManual && (
          <Button size="sm" onClick={connect} disabled={disabled || phase === "starting"}>
            {phase === "starting" ? "Opening…" : `Connect ${label}`}
          </Button>
        )}
        {/* Once the sign-in is done the agent is still parked: it re-reads the
            database rather than trusting the browser, so the user has to say
            they finished. */}
        {(phase === "browser" || phase === "starting") && (
          <Button size="sm" variant="secondary" onClick={() => onAnswer({ connected: true })} disabled={disabled}>
            I've connected it
          </Button>
        )}
        <button
          type="button"
          onClick={() => onAnswer({ skipped: true })}
          disabled={disabled}
          className="text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
        >
          Skip — carry on without it
        </button>
      </div>

      {phase === "browser" && (
        <p className="text-xs text-muted-foreground">
          Finish signing in in your browser, then come back and press “I've connected it”.
        </p>
      )}
      <p className="text-[11px] text-muted-foreground/70">
        Skipping is fine — Duct will say what it couldn't check.
      </p>
    </div>
  );
}
