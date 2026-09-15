"use client";

// The desktop shell's one data switch: crash reports and usage analytics.
//
// Deliberately one switch rather than two. Both answer the same question —
// "does Duct learn anything from my running it" — and splitting them buys a
// distinction nobody asked for at the cost of a settings screen nobody reads.
//
// Renders nothing anywhere else — and nothing in a desktop build compiled
// without a DSN, where the switch would change a preference that no code reads.
// An off switch that does not switch anything off is worse than no switch.
//
// The copy is deliberately specific about what is and isn't sent. "Help us
// improve Duct" tells someone nothing they can consent to.
//
// It is a list rather than a paragraph, which is the second half of the same
// argument. The prose version ran seventy-two words — it argued for the
// feature, then named what is sent, then what is never sent, all in one
// block under a switch. The reader's question is binary and comparative
// ("what leaves my machine?"), and a paragraph is the worst shape for a
// comparison: the "never" half arrives as a subordinate clause at the end,
// which is exactly where a skimmer stops.

import { useCallback, useEffect, useState } from "react";
import { Check, Minus, ShieldAlert } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { getTelemetrySettings, setTelemetryEnabled } from "@/lib/telemetry";

export default function TelemetryCard() {
  const [state, setState] = useState({ available: false, enabled: false, defaultOn: false });
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
    <TelemetryPanel
      enabled={state.enabled}
      defaultOn={state.defaultOn}
      busy={busy}
      error={error}
      onToggle={toggle}
    />
  );
}

/**
 * The card itself, with no backend behind it — exported for the same reason
 * `UsageEmpty` is: `/preview` has no desktop shell to ask, and a component that
 * renders `null` everywhere but a signed Tauri build is a component nobody can
 * look at.
 */
export function TelemetryPanel({ enabled, defaultOn, busy = false, error = "", onToggle }) {
  return (
    <article className="conn-panel">
      <span className="conn-tile-logo" aria-hidden="true">
        <ShieldAlert size={20} strokeWidth={1.7} />
      </span>
      <div className="conn-tile-body">
        <div className="conn-tile-top">
          <span className="conn-tile-title">Crash reports &amp; usage</span>
          <Switch
            checked={enabled}
            onCheckedChange={onToggle}
            disabled={busy}
            aria-label="Send crash reports and usage data"
          />
        </div>
        <p className="conn-tile-desc">
          {defaultOn
            ? "On by default, so a crash tells us something without you having to report it."
            : "Off by default — Duct runs its backend here, and nothing leaves unless you say so."}
        </p>

        {/* Two columns, not two paragraphs: the promise is only legible next
            to what it excludes. Muted rather than destructive on the right —
            "we never send this" is a reassurance, not a warning. */}
        <dl className="mt-2.5 grid gap-x-5 gap-y-1 text-xs leading-snug @md:grid-cols-2">
          <div>
            <dt className="mb-1 font-medium text-foreground">Sends</dt>
            {["The error and stack trace of a crash", "Which screens and features you open"].map((row) => (
              <dd key={row} className="flex items-start gap-1.5 text-muted-foreground">
                <Check className="mt-0.5 size-3 shrink-0 text-success" aria-hidden="true" />
                {row}
              </dd>
            ))}
          </div>
          <div>
            <dt className="mb-1 font-medium text-foreground">Never sends</dt>
            {["Your provider API keys", "Your data, or anything you generate"].map((row) => (
              <dd key={row} className="flex items-start gap-1.5 text-muted-foreground">
                <Minus className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                {row}
              </dd>
            ))}
          </div>
        </dl>

        <p className="mt-2 text-2xs text-muted-foreground">
          Applies to the bundled backend next time you open Duct.
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
