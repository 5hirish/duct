"use client";

// What happens when the model you picked is out of quota.
//
// The copy names the consequence rather than the mechanism. "Automatic model
// fallback" describes what the code does and tells the person deciding
// nothing; "your 9am brief still arrives, written by your Standard model"
// tells them what they are choosing between. The off state gets the same
// treatment — it is a legitimate choice, so it is described as a choice and
// not as a warning.
//
// It reads the ladder the user already configured above rather than asking for
// a second one. That is the whole reason this is a switch and not another
// picker: the fallback order is the three models they have already chosen, in
// the order they already put them in.

import { useCallback, useEffect, useState } from "react";
import { LifeBuoy } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { fetchModelSettings, saveModelSettings } from "@/lib/modelSettings";

export default function AutoFallbackCard({ ladder = [] }) {
  const [enabled, setEnabled] = useState(true);
  const [signedOut, setSignedOut] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchModelSettings().then((settings) => {
      if (alive) setEnabled(settings.auto_fallback);
    });
    return () => {
      alive = false;
    };
  }, []);

  const toggle = useCallback(async (next) => {
    setEnabled(next);
    const saved = await saveModelSettings({ auto_fallback: next });
    // A preference that silently did not save is the one that erodes trust in
    // every other control on the page.
    setSignedOut(saved === null);
  }, []);

  // Named tiers, not model ids: the sentence is about which of *their* choices
  // steps in, and a model id makes it read like a system message.
  const chain = ladder.join(" → ");

  return (
    <article className="conn-panel">
      <span className="conn-tile-logo" aria-hidden="true">
        <LifeBuoy size={20} strokeWidth={1.7} />
      </span>
      <div className="conn-tile-body">
        <div className="conn-tile-top">
          <span className="conn-tile-title">Keep working when you hit a limit</span>
          <Switch
            checked={enabled}
            onCheckedChange={toggle}
            aria-label="Use the next model down when a provider is out of quota"
          />
        </div>
        <p className="conn-tile-desc">
          {enabled
            ? `When a provider says you are out of quota, Duct runs the job on the next model down${chain ? ` — ${chain}` : ""} — and tells you which one it used. Your scheduled brief still arrives.`
            : "When a provider says you are out of quota, the run stops and shows you the limit. Nothing switches models on your behalf — including your scheduled brief, which will not arrive that morning."}
        </p>
        {signedOut && (
          <p className="conn-tile-desc mt-warn">
            Not saved — sign in to keep this setting across your devices.
          </p>
        )}
      </div>
    </article>
  );
}
