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
import { ShieldAlert } from "lucide-react";
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
    <article className="conn-panel">
      <span className="conn-tile-logo" aria-hidden="true">
        <ShieldAlert size={20} strokeWidth={1.7} />
      </span>
      <div className="conn-tile-body">
        <div className="conn-tile-top">
          <span className="conn-tile-title">Crash reports</span>
          <Switch
            checked={state.enabled}
            onCheckedChange={toggle}
            disabled={busy}
            aria-label="Send crash reports"
          />
        </div>
        <p className="conn-tile-desc">
          Off by default. Duct runs its backend on this machine, so nothing
          leaves it unless you say so. When on, it sends the error and the
          stack trace that caused a crash — never your provider API keys, your
          data, or anything you generate. Takes effect for the bundled backend
          the next time you open Duct.
        </p>

        {error && (
          <p role="alert" className="text-destructive" style={{ marginTop: 6, fontSize: 12 }}>
            {error}
          </p>
        )}
      </div>
    </article>
  );
}
