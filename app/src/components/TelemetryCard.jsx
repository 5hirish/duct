"use client";

// Crash-reporting consent, desktop only.
//
// Renders nothing anywhere else — and nothing in a desktop build compiled
// without a DSN, where the switch would change a preference that no code reads.
// An off switch that does not switch anything off is worse than no switch.
//
// The copy is deliberately specific about what is and isn't sent. "Help us
// improve Duct" tells someone nothing they can consent to.

import { useCallback, useEffect, useState } from "react";
import { Switch } from "@/components/ui/switch";
import { getTelemetrySettings, setTelemetryEnabled } from "@/lib/telemetry";

export default function TelemetryCard() {
  const [state, setState] = useState({ available: false, enabled: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    getTelemetrySettings().then((next) => {
      if (alive) setState(next);
    });
    return () => {
      alive = false;
    };
  }, []);

  const toggle = useCallback(
    async (next) => {
      setBusy(true);
      setError("");
      try {
        await setTelemetryEnabled(next);
        setState((prev) => ({ ...prev, enabled: next }));
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  if (!state.available) return null;

  return (
    <article className="connection-card">
      <div className="connection-card-head">
        <div>
          <h2 className="connection-title">Crash reports</h2>
          <p className="connection-description">
            Off by default. Duct runs its backend on this machine, so nothing
            leaves it unless you say so.
          </p>
        </div>
        <Switch
          checked={state.enabled}
          onCheckedChange={toggle}
          disabled={busy}
          aria-label="Send crash reports"
        />
      </div>

      <p className="app-subtle" style={{ fontSize: 12, lineHeight: 1.55, marginTop: 8 }}>
        When on, Duct sends the error and the stack trace that caused a crash.
        It never sends your provider API keys, your data, or the contents of
        anything you generate. Takes effect for the bundled backend the next
        time you open Duct.
      </p>

      {error && (
        <p role="alert" className="text-destructive" style={{ marginTop: 6, fontSize: 12 }}>
          {error}
        </p>
      )}
    </article>
  );
}
