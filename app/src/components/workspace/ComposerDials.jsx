"use client";

// The dials a message runs with, in a composer: how freely Duct may act, which
// tier it starts on, and how hard the model thinks.
//
// One component for the desk composer and the session composer, because they
// were drifting: the desk had two of these and the session had none, so the
// person who chose a posture on the desk could not see or change it once the
// conversation was open. All three are persisted settings, not per-message
// decoration — the posture writes to the project, the other two to the
// user's preferences.
//
// Placement follows how often each one changes, which is also when it binds:
//   autonomy — the next message (backend/routes/agents.py re-reads the project
//              per turn and re-states the posture to the agent). It is the one
//              dial a person flips mid-conversation, so it sits inline on the
//              left, folded to the current posture.
//   tier + thinking — the next session: both bind when the agent is built,
//              and a running thread keeps what it opened with. One control on
//              the right beside the ring and Send, as quiet text (TierDial):
//              which model answers is the one choice people look for by name,
//              the way every chat app puts the model name at the corner of
//              the box, and how hard it thinks is a property of that choice,
//              so it is a stepped slider under the tier list rather than a
//              menu of its own. The panel is a Popover, not a DropdownMenu: a
//              menu roves focus over its items and swallows Tab, so a slider
//              inside one is mouse-only.
//
// Four labelled pills used to sit in the footer, three of them reading "auto"
// and none of the three acting on the message being typed; a control in a
// composer footer promises "this message", and that row broke the promise
// three times out of four. The brief's shape (`preferred_artifact_format`)
// was the last of those pills to go: it is a per-brief trade the agent can
// make itself, and a picker for it in every composer taxed everyone to
// serve the few who cared. The preference still exists and the backend
// still reads it; it has no composer control.
//
// The thinking picker is server-driven. Every provider sells this dial under a
// different name with a different ladder, so Duct names four rungs and
// backend/agents/thinking.py maps them per model. The menu shows the resolved
// native value under each rung, which is the honesty clause: the abstraction
// saves you from learning five dialects, it does not hide which one is in use.
// A model with no dial (Gemini 2.5, Haiku 4.5, gpt-4o) shows no slider.

import { useEffect, useState } from "react";
import { Anvil, ChevronDown, Feather, Scale } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AUTONOMY_OPTIONS, setProjectAutonomy } from "@/lib/projectsApi";
import { loadPreferences, savePreferences } from "@/lib/userPreferences";
import { DEFAULT_ENGINE } from "@/lib/engines";
import { TIERS } from "@/lib/modelTiers";
import { NO_THINKING, fetchThinking } from "@/lib/thinking";
import { cn } from "@/lib/utils";

// The stored value for "let Duct decide" is "", which a Radix radio group
// cannot hold — it treats an empty string as no selection.
const AUTO = "auto";

const TIER_ICONS = { heavy: Anvil, standard: Scale, light: Feather };

// A stored preference, read after mount. The composer is server-rendered, and
// a useState initialiser that reads localStorage renders one value on the
// server and another in the browser, which React reports as a hydration
// mismatch and re-renders the whole tree to repair. The first paint shows the
// default for one frame; the stored value lands in the effect.
function useStoredPreference(key, fallback) {
  const [value, setValue] = useState(fallback);
  useEffect(() => {
    setValue(loadPreferences()[key] || fallback);
  }, [key, fallback]);
  function save(next) {
    setValue(next);
    savePreferences({ ...loadPreferences(), [key]: next });
  }
  return [value, save];
}

const NEXT_SESSION = msg`Applies from your next session`;

/** A quiet last line in a menu saying when the choice takes effect. */
function Applies({ text }) {
  return (
    <p className="border-t px-3 pb-1 pt-1.5 text-2xs text-muted-foreground">{text}</p>
  );
}

/**
 * How freely Duct may act, as a segmented control that rests folded: only
 * the current posture shows, and the other two unfold beside it on hover or
 * keyboard focus, or on a tap of the visible one where there is no hover.
 * Three words and no menu, because it is the one dial flipped
 * mid-conversation — "ask me first for this one" — and a Select hid which
 * two postures were not chosen; folded, because a footer that always shows
 * all three reads as three settings when it is one. The blurbs, which used
 * to be the menu rows, are tooltips now.
 */
export function AutonomyDial({ projectId, value, onChange, deferred = false }) {
  const { t, i18n } = useLingui();
  // Pinned open by a tap on the visible choice: touch has no hover, and a
  // control that only unfolds under a pointer is a control a phone cannot
  // change. Picking any posture folds it again.
  const [pinned, setPinned] = useState(false);

  async function pick(next) {
    setPinned(false);
    if (next === value) return;
    onChange?.(next);
    if (!projectId) return;
    try {
      await setProjectAutonomy(projectId, next);
    } catch {
      /* the picker is a hint; the backend is the authority on next request */
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label={t`How freely Duct may act`}
      data-open={pinned || undefined}
      className="group/posture inline-flex h-7 items-center rounded-full bg-muted p-0.5"
      onMouseLeave={() => setPinned(false)}
    >
      {AUTONOMY_OPTIONS.map((o) => {
        const active = o.value === value;
        return (
          <Tooltip key={o.value}>
            <TooltipTrigger asChild>
              <button
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => (active ? setPinned((open) => !open) : pick(o.value))}
                className={cn(
                  // Every choice stays in flow; the two not chosen fold to
                  // zero width and fade, and unfold on hover, focus or a
                  // pin. A width transition rather than display:none is
                  // what makes it a motion instead of a pop.
                  "inline-flex h-6 items-center justify-center overflow-hidden whitespace-nowrap rounded-full text-xs leading-none",
                  "transition-[max-width,padding,opacity] duration-200 ease-out",
                  active
                    ? "max-w-32 bg-background px-2.5 text-foreground shadow-sm"
                    : "max-w-0 px-0 text-muted-foreground opacity-0 hover:text-foreground " +
                      "group-hover/posture:max-w-32 group-hover/posture:px-2.5 group-hover/posture:opacity-100 " +
                      "group-focus-within/posture:max-w-32 group-focus-within/posture:px-2.5 group-focus-within/posture:opacity-100 " +
                      "group-data-open/posture:max-w-32 group-data-open/posture:px-2.5 group-data-open/posture:opacity-100",
                )}
              >
                {i18n._(o.label)}
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-[260px]">
              {/* One block: TooltipContent lays its children out in a row,
                  and two paragraphs side by side read as two tooltips. */}
              <span className="block">
                <span className="block">{i18n._(o.blurb)}</span>
                {deferred && <span className="mt-1 block text-2xs opacity-70">{t`Applies from your next message`}</span>}
              </span>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}

/** The thinking rungs the current engine's model offers, or nothing. */
function useThinkingDial(engine) {
  // Which rungs exist depends on the model the engine resolves to, so the
  // server answers it. Until it does — or when the model has no dial — the
  // submenu simply isn't there.
  const [dial, setDial] = useState(NO_THINKING);
  useEffect(() => {
    let alive = true;
    fetchThinking(engine).then((d) => alive && setDial(d));
    return () => {
      alive = false;
    };
  }, [engine]);
  return dial;
}

/** One choice in the tier list, as a plain button so Tab reaches it inside
 *  the popover.
 *
 *  Chosen is a primary border over a faint primary wash — the same thing a
 *  chosen radio card says everywhere else in this app (the execution ladder
 *  on /execute, the writing presets on /settings/profile). It replaces a
 *  6px dot in a 36px gutter, which marked one row by indenting all four and
 *  still did not read as chosen. The border is on every row, transparent
 *  until it is the one, so nothing moves when the choice does. */
function TierChoice({ checked, onSelect, label, blurb }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onSelect}
      className={cn(
        "flex w-full cursor-default select-none flex-col items-start gap-0.5 rounded-2xl border px-3 py-2 text-left outline-none transition-colors",
        checked
          ? "border-primary bg-primary/10"
          : "border-transparent hover:bg-accent focus-visible:bg-accent",
      )}
    >
      <span className={cn("text-sm", checked && "font-medium")}>{label}</span>
      <span className="text-2xs leading-snug text-muted-foreground">{blurb}</span>
    </button>
  );
}

/** How hard the model thinks, as a stepped slider: Auto at the left, then
 *  the rungs this model offers. Auto is a real stop rather than a switch
 *  because it is a real choice — send nothing, let the model do what it
 *  would have done. The word beside the title names the stop under the
 *  thumb, the dots on the track are the scale, and the line below says what
 *  the stop buys. No words under the track: they were tried and read as a
 *  second control. The native value each rung maps to (thinking.py) is not
 *  shown here either — it read as noise — and stays on the Models page. */
function ThinkingSlider({ dial, value, onPick }) {
  const { t } = useLingui();
  const stops = [
    { level: "", label: t`Auto`, blurb: t`Whatever this model does anyway` },
    ...dial.levels.map((level) => ({ level: level.level, label: level.label, blurb: level.blurb })),
  ];
  const index = Math.max(0, stops.findIndex((stop) => stop.level === value));
  const current = stops[index];
  return (
    <div className="px-3 pb-1.5 pt-2">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span id="thinking-slider-label">{t`Thinking`}</span>
        <span className="text-xs text-muted-foreground">{current.label}</span>
      </div>
      <Slider
        className="mt-3"
        marks
        min={0}
        max={stops.length - 1}
        step={1}
        value={[index]}
        onValueChange={([next]) => onPick(stops[next].level)}
        aria-labelledby="thinking-slider-label"
        aria-valuetext={current.label}
      />
      <p className="mt-2 text-2xs leading-snug text-muted-foreground">{current.blurb}</p>
    </div>
  );
}

/** Which tier the run starts on and how hard it thinks, as quiet text on the
 * composer's right. Duct assigns a tier per job (backend/agents/tiers.py);
 * this lifts or lowers the starting rung for the pass that writes the answer,
 * and the run still steps down the ladder if that rung cannot serve. Which
 * model each tier means is set once in Settings → Models, so the control
 * names the tier, not a model id. */
export function TierDial({ engine = DEFAULT_ENGINE, deferred = false }) {
  const { t, i18n } = useLingui();
  const dial = useThinkingDial(engine);
  const [tier, saveTier] = useStoredPreference("tier", "");
  const [thinking, saveThinking] = useStoredPreference("thinking", "");
  const chosen = TIERS.find((option) => option.key === tier);
  const Icon = chosen ? TIER_ICONS[chosen.key] : Scale;
  const label = chosen ? i18n._(chosen.label) : t`Auto`;
  // The trigger reads like "Sonnet 5 · Medium": the tier, then the thinking
  // rung only when one is set, since Auto beside Auto says nothing twice.
  const thinkingLabel = dial.supported ? dial.levels.find((l) => l.level === thinking)?.label : "";
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          aria-label={t`Which model tier runs this, and how hard it thinks`}
          className="h-8 gap-1 px-2 font-normal text-muted-foreground"
        >
          <Icon aria-hidden />
          <span>{label}</span>
          {thinkingLabel && <span className="opacity-70">{thinkingLabel}</span>}
          <ChevronDown className="size-3 opacity-60" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[300px]">
        <div role="radiogroup" aria-label={t`Which model tier runs this`}>
          <TierChoice
            checked={!tier}
            onSelect={() => saveTier("")}
            label={t`Auto`}
            blurb={t`Duct's pick for the job — Heavy for a brief, Standard for a follow-up`}
          />
          {TIERS.map((option) => (
            <TierChoice
              key={option.key}
              checked={tier === option.key}
              onSelect={() => saveTier(option.key)}
              label={i18n._(option.label)}
              blurb={i18n._(option.tagline)}
            />
          ))}
        </div>
        {dial.supported && (
          <>
            <div className="-mx-1 my-1 h-px bg-border" />
            <ThinkingSlider dial={dial} value={thinking} onPick={saveThinking} />
          </>
        )}
        <Applies text={deferred ? i18n._(NEXT_SESSION) : t`Which model each tier means is set in Settings → Models`} />
      </PopoverContent>
    </Popover>
  );
}

export default function ComposerDials({
  projectId,
  autonomy,
  onAutonomyChange,
  // True inside a running session, where autonomy binds at the next message
  // — the tooltips say so.
  deferred = false,
}) {
  // The left cluster only; TierDial is the caller's to place on the right,
  // beside the ring and Send. One control today, kept as the seam so the
  // desk and the session composer keep sharing whatever the left holds.
  return <AutonomyDial projectId={projectId} value={autonomy} onChange={onAutonomyChange} deferred={deferred} />;
}
