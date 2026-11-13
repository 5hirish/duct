"use client";

// Whether the insights agent may compute in this app, and how much it may use.
//
// The agent's figures come from Python it runs here, in a Web Worker with no
// network (public/python-worker.js). The limits are per device on purpose:
// they describe what this machine's browser survives, which is not the same on
// an 8 GB laptop and a 32 GB desktop, so they live beside the composer's other
// per-device dials in localStorage and ride on each request.
//
// The copy for "off" says what the person loses in their terms: the agent
// stops computing and tells them which figures it could not work out, rather
// than "disables code execution", which describes a mechanism.

import { useCallback, useEffect, useId, useState } from "react";
import { Code } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { loadPreferences, savePreferences, PREFS_DEFAULTS } from "@/lib/userPreferences";

// Mirrors of the backend ceilings (agents/insights/python_run.py). The server
// clamps anyway; these keep the field from accepting a value it will not use.
const ROWS_MIN = 1_000;
const ROWS_MAX = 500_000;
const SECONDS_MIN = 5;
const SECONDS_MAX = 300;

const clamp = (value, min, max, fallback) => {
  const n = Math.round(Number(value));
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
};

export default function RunPythonCard() {
  const { t } = useLingui();
  const rowsId = useId();
  const secondsId = useId();
  const [enabled, setEnabled] = useState(PREFS_DEFAULTS.run_python);
  const [rows, setRows] = useState(String(PREFS_DEFAULTS.run_python_max_rows));
  const [seconds, setSeconds] = useState(String(PREFS_DEFAULTS.run_python_timeout_seconds));

  // localStorage only exists after mount; reading it during render would
  // differ between server and client.
  useEffect(() => {
    const prefs = loadPreferences();
    setEnabled(prefs.run_python);
    setRows(String(prefs.run_python_max_rows));
    setSeconds(String(prefs.run_python_timeout_seconds));
  }, []);

  const save = useCallback((patch) => savePreferences({ ...loadPreferences(), ...patch }), []);

  const toggle = useCallback((next) => {
    setEnabled(next);
    save({ run_python: next });
  }, [save]);

  // Saved on blur, clamped: a half-typed "5" must not become the limit while
  // someone is on their way to "50000".
  const commitRows = useCallback(() => {
    const value = clamp(rows, ROWS_MIN, ROWS_MAX, PREFS_DEFAULTS.run_python_max_rows);
    setRows(String(value));
    save({ run_python_max_rows: value });
  }, [rows, save]);

  const commitSeconds = useCallback(() => {
    const value = clamp(seconds, SECONDS_MIN, SECONDS_MAX, PREFS_DEFAULTS.run_python_timeout_seconds);
    setSeconds(String(value));
    save({ run_python_timeout_seconds: value });
  }, [seconds, save]);

  return (
    <article className="conn-panel">
      <span className="conn-tile-logo" aria-hidden="true">
        <Code size={20} strokeWidth={1.7} />
      </span>
      <div className="conn-tile-body">
        <div className="conn-tile-top">
          <span className="conn-tile-title"><Trans>Compute with Python</Trans></span>
          <Switch
            checked={enabled}
            onCheckedChange={toggle}
            aria-label={t`Let the insights agent compute its figures with Python in this app`}
          />
        </div>
        <p className="conn-tile-desc">
          {enabled
            ? t`The agent works out totals, shares and trends with Python that runs here, on this device, with no internet access. Figures in a brief are computed, not estimated.`
            : t`The agent works figures out without running code, and says which ones it could not compute.`}
        </p>
        {enabled && (
          <div className="mt-3 grid gap-3 @md:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor={rowsId}><Trans>Rows per run</Trans></Label>
              <Input
                id={rowsId}
                type="number"
                inputMode="numeric"
                min={ROWS_MIN}
                max={ROWS_MAX}
                step={1000}
                value={rows}
                onChange={(e) => setRows(e.target.value)}
                onBlur={commitRows}
              />
              <p className="text-2xs text-muted-foreground">
                <Trans>Lower it if this device runs short of memory.</Trans>
              </p>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={secondsId}><Trans>Time limit (seconds)</Trans></Label>
              <Input
                id={secondsId}
                type="number"
                inputMode="numeric"
                min={SECONDS_MIN}
                max={SECONDS_MAX}
                value={seconds}
                onChange={(e) => setSeconds(e.target.value)}
                onBlur={commitSeconds}
              />
              <p className="text-2xs text-muted-foreground">
                <Trans>A run that takes longer is stopped.</Trans>
              </p>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
