"use client";

// How connector data is written on its way to the model.
//
// The copy names both states in terms of what the user gets back, because the
// honest description of "off" is not "you get the raw data" — it is "a large
// pull gets cut short and the brief is written without those rows". Someone
// deciding this needs that sentence; "reduces token usage" would let them turn
// on data loss believing they were saving money.
//
// On by default, and it stays a switch only so that anyone who suspects the
// shape of their data can rule it out in one click and say so in a bug report.

import { useCallback, useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { loadPreferences, savePreferences, PREFS_DEFAULTS } from "@/lib/userPreferences";

export default function ContextCompressionCard() {
  const [enabled, setEnabled] = useState(PREFS_DEFAULTS.context_compression);

  // Preferences live in localStorage, so the first paint has to be the default
  // and the stored value arrives after mount — reading during render would
  // differ between server and client and blow up hydration.
  useEffect(() => {
    setEnabled(loadPreferences().context_compression);
  }, []);

  const toggle = useCallback((next) => {
    setEnabled(next);
    savePreferences({ ...loadPreferences(), context_compression: next });
  }, []);

  return (
    <article className="conn-panel">
      <span className="conn-tile-logo" aria-hidden="true">
        <Layers size={20} strokeWidth={1.7} />
      </span>
      <div className="conn-tile-body">
        <div className="conn-tile-top">
          <span className="conn-tile-title">Context compression</span>
          <Switch
            checked={enabled}
            onCheckedChange={toggle}
            aria-label="Compress connector data before it reaches the model"
          />
        </div>
        <p className="conn-tile-desc">
          {enabled
            ? "Your analytics rows reach the model as a compact table instead of raw JSON — about half the tokens, with every row and every number unchanged."
            : "Your analytics rows reach the model as raw JSON. A large pull gets cut short before the model sees all of it, so a brief may be written without the rows that were dropped."}
        </p>
      </div>
    </article>
  );
}
