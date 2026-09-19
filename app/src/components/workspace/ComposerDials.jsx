"use client";

// The dials a message runs with, as chips in a composer: how freely Duct may
// act, how hard the model thinks, and which tier it starts on.
//
// One component for the desk composer and the session composer, because they
// were drifting: the desk had two of these and the session had none, so the
// person who chose a posture on the desk could not see or change it once the
// conversation was open. All three are persisted settings, not per-message
// decoration — the posture writes to the project, the other two to the
// user's preferences — and each chip says where its change lands.
//
// What applies when differs, and the menu says so rather than pretending:
//   autonomy — the next message (backend/routes/agents.py re-reads the project
//              per turn and re-states the posture to the agent);
//   thinking, tier — the next session: both bind the model when the agent is
//              built, and a running thread keeps the model it opened with.
//
// The thinking picker is server-driven. Every provider sells this dial under a
// different name with a different ladder, so Duct names four rungs and
// backend/agents/thinking.py maps them per model. The menu shows the resolved
// native value under each rung, which is the honesty clause: the abstraction
// saves you from learning five dialects, it does not hide which one is in use.
// A model with no dial (Gemini 2.5, Haiku 4.5, gpt-4o) shows no control.

import { useEffect, useState } from "react";
import { Anvil, Feather, Scale, Sparkles } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { AUTONOMY_OPTIONS, setProjectAutonomy } from "@/lib/projectsApi";
import { loadPreferences, savePreferences } from "@/lib/userPreferences";
import { DEFAULT_ENGINE } from "@/lib/engines";
import { TIERS } from "@/lib/modelTiers";
import { NO_THINKING, fetchThinking, levelHint } from "@/lib/thinking";

// All three read as chips — the same object as the project chip above the
// desk box, because they are the same kind of thing: what this message will
// run with. Height comes from the trigger's own size="sm" (h-8) — a bare h-7
// here loses to the component's data-[size] variant.
const CHIP =
  "gap-1.5 rounded-full border bg-transparent px-2.5 text-xs text-muted-foreground " +
  "shadow-none hover:bg-accent hover:text-foreground focus-visible:ring-0";

// The stored value for "let Duct decide" is "", which a Select cannot hold —
// Radix treats an empty string as no selection.
const AUTO = "auto";

const TIER_ICONS = { heavy: Anvil, standard: Scale, light: Feather };

const NEXT_SESSION = msg`Applies from your next session`;

function Row({ label, blurb, hint }) {
  return (
    <span className="flex flex-col items-start gap-0.5">
      <span>{label}</span>
      {blurb && <span className="text-2xs leading-snug text-muted-foreground">{blurb}</span>}
      {hint && <span className="text-2xs font-mono text-muted-foreground">{hint}</span>}
    </span>
  );
}

/** A quiet last line in a menu saying when the choice takes effect. */
function Applies({ text }) {
  return (
    <p className="border-t px-2 pb-1 pt-1.5 text-2xs text-muted-foreground">{text}</p>
  );
}

export function AutonomyDial({ projectId, value, onChange, deferred = false }) {
  const { t, i18n } = useLingui();
  const found = AUTONOMY_OPTIONS.find((o) => o.value === value);
  const label = found ? i18n._(found.label) : t`Ask`;

  async function pick(next) {
    onChange?.(next);
    if (!projectId) return;
    try {
      await setProjectAutonomy(projectId, next);
    } catch {
      /* the picker is a hint; the backend is the authority on next request */
    }
  }

  return (
    <Select value={value} onValueChange={pick}>
      <SelectTrigger size="sm" className={CHIP} aria-label={t`How freely Duct may act`}>
        <span>{label}</span>
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="max-w-[320px]">
        {AUTONOMY_OPTIONS.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            <Row label={i18n._(o.label)} blurb={i18n._(o.blurb)} />
          </SelectItem>
        ))}
        {deferred && <Applies text={t`Applies from your next message`} />}
      </SelectContent>
    </Select>
  );
}

export function ThinkingDial({ engine = DEFAULT_ENGINE, deferred = false }) {
  const { t, i18n } = useLingui();
  const [thinking, setThinking] = useState(() => loadPreferences().thinking || "");
  // Which rungs exist depends on the model the engine resolves to, so the
  // server answers it. Until it does — or when the model has no dial — the
  // control simply isn't there.
  const [dial, setDial] = useState(NO_THINKING);

  useEffect(() => {
    let alive = true;
    fetchThinking(engine).then((d) => alive && setDial(d));
    return () => {
      alive = false;
    };
  }, [engine]);

  if (!dial.supported) return null;

  // The chip says the Duct word; the menu says which provider word it becomes.
  const label = dial.levels.find((l) => l.level === thinking)?.label.toLowerCase() || t`auto`;
  const dialName = dial.dial;
  const dialDefault = dial.default_native;

  function pick(value) {
    const next = value === AUTO ? "" : value;
    setThinking(next);
    savePreferences({ ...loadPreferences(), thinking: next });
  }

  return (
    <Select value={thinking || AUTO} onValueChange={pick}>
      <SelectTrigger size="sm" className={CHIP} aria-label={t`How hard the model should think`}>
        <Sparkles className="size-3" aria-hidden />
        <span><Trans>Thinking: {label}</Trans></span>
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="max-w-[320px]">
        {/* "Auto" is not a fifth rung — it sends nothing, so the model does
            whatever it would have done. */}
        <SelectItem value={AUTO}>
          <Row label={t`Auto`} blurb={t`${dialName} ${dialDefault} · whatever this model does anyway`} />
        </SelectItem>
        {dial.levels.map((level) => (
          <SelectItem key={level.level} value={level.level}>
            <Row label={level.label} blurb={level.blurb} hint={levelHint(level, dial.dial)} />
          </SelectItem>
        ))}
        {deferred && <Applies text={i18n._(NEXT_SESSION)} />}
      </SelectContent>
    </Select>
  );
}

/** Which tier the run starts on. Duct assigns a tier per job
 * (backend/agents/tiers.py); this lifts or lowers the starting rung for the
 * pass that writes the answer, and the run still steps down the ladder if
 * that rung cannot serve. Which model each tier means is set once in
 * Settings → Models, so the menu names the tier, not a model id. */
export function TierDial({ deferred = false }) {
  const { t, i18n } = useLingui();
  const [tier, setTier] = useState(() => loadPreferences().tier || "");
  const chosen = TIERS.find((option) => option.key === tier);
  const Icon = chosen ? TIER_ICONS[chosen.key] : Scale;
  const label = chosen ? chosen.label.toLowerCase() : t`auto`;

  function pick(value) {
    const next = value === AUTO ? "" : value;
    setTier(next);
    savePreferences({ ...loadPreferences(), tier: next });
  }

  return (
    <Select value={tier || AUTO} onValueChange={pick}>
      <SelectTrigger size="sm" className={CHIP} aria-label={t`Which model tier runs this`}>
        <Icon className="size-3" aria-hidden />
        <span><Trans>Model: {label}</Trans></span>
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="max-w-[320px]">
        <SelectItem value={AUTO}>
          <Row label={t`Auto`} blurb={t`Duct's pick for the job — Heavy for a brief, Standard for a follow-up`} />
        </SelectItem>
        {TIERS.map((option) => (
          <SelectItem key={option.key} value={option.key}>
            <Row label={i18n._(option.label)} blurb={i18n._(option.tagline)} />
          </SelectItem>
        ))}
        <Applies text={deferred ? i18n._(NEXT_SESSION) : t`Which model each tier means is set in Settings → Models`} />
      </SelectContent>
    </Select>
  );
}

export default function ComposerDials({
  projectId,
  autonomy,
  onAutonomyChange,
  engine = DEFAULT_ENGINE,
  // True inside a running session, where thinking and tier bind at the next
  // session and autonomy at the next message — the menus say so.
  deferred = false,
}) {
  // `contents`, not a flex box of its own: the chips wrap in the composer's
  // footer row together with the attach button, so at phone width the row
  // breaks between chips rather than leaving the paperclip alone on a line.
  return (
    <div className="contents">
      <AutonomyDial projectId={projectId} value={autonomy} onChange={onAutonomyChange} deferred={deferred} />
      <ThinkingDial engine={engine} deferred={deferred} />
      <TierDial deferred={deferred} />
    </div>
  );
}
