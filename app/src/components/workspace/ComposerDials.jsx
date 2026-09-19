"use client";

// The dials a message runs with, as chips in a composer: how freely Duct may
// act, how hard the model thinks, which tier it starts on, and what shape the
// brief takes.
//
// One component for the desk composer and the session composer, because they
// were drifting: the desk had two of these and the session had none, so the
// person who chose a posture on the desk could not see or change it once the
// conversation was open. All four are persisted settings, not per-message
// decoration — the posture writes to the project, the other three to the
// user's preferences — and each chip says where its change lands.
//
// What applies when differs, and the menu says so rather than pretending:
//   autonomy — the next message (backend/routes/agents.py re-reads the project
//              per turn and re-states the posture to the agent);
//   thinking, tier, brief — the next session: all three bind when the agent
//              is built, and a running thread keeps what it opened with.
//
// The thinking picker is server-driven. Every provider sells this dial under a
// different name with a different ladder, so Duct names four rungs and
// backend/agents/thinking.py maps them per model. The menu shows the resolved
// native value under each rung, which is the honesty clause: the abstraction
// saves you from learning five dialects, it does not hide which one is in use.
// A model with no dial (Gemini 2.5, Haiku 4.5, gpt-4o) shows no control.

import { useEffect, useState } from "react";
import { Anvil, Feather, FileText, LayoutTemplate, Scale, Sparkles, WandSparkles } from "lucide-react";
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

// The shape of a brief. The blurbs carry the trade the person is making —
// tokens against layout — because a format name alone reads as a file
// extension. "auto" is a real stored value here, unlike the other dials: the
// backend reads it as "the agent chooses per brief and says so".
export const BRIEF_FORMATS = [
  {
    value: "html",
    label: "HTML",
    Icon: LayoutTemplate,
    blurb: "A styled page with its own charts and sortable tables. Costs more to write, reads better, forwards as one file",
  },
  {
    value: "markdown",
    label: "Markdown",
    Icon: FileText,
    blurb: "Fast and cheaper. Headings, text and tables; pastes into a doc",
  },
  {
    value: "auto",
    label: "Auto",
    Icon: WandSparkles,
    blurb: "Duct picks per brief: markdown for a short read, a page when layout or a chart earns it",
  },
];
const DEFAULT_BRIEF_FORMAT = "html";

const NEXT_SESSION = "Applies from your next session";

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
  const label = AUTONOMY_OPTIONS.find((o) => o.value === value)?.label || "Ask";

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
      <SelectTrigger size="sm" className={CHIP} aria-label="How freely Duct may act">
        <span>{label}</span>
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="max-w-[320px]">
        {AUTONOMY_OPTIONS.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            <Row label={o.label} blurb={o.blurb} />
          </SelectItem>
        ))}
        {deferred && <Applies text="Applies from your next message" />}
      </SelectContent>
    </Select>
  );
}

export function ThinkingDial({ engine = DEFAULT_ENGINE, deferred = false }) {
  const [thinking, saveThinking] = useStoredPreference("thinking", "");
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
  const label = dial.levels.find((l) => l.level === thinking)?.label.toLowerCase() || "auto";

  function pick(value) {
    saveThinking(value === AUTO ? "" : value);
  }

  return (
    <Select value={thinking || AUTO} onValueChange={pick}>
      <SelectTrigger size="sm" className={CHIP} aria-label="How hard the model should think">
        <Sparkles className="size-3" aria-hidden />
        <span>Thinking: {label}</span>
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="max-w-[320px]">
        {/* "Auto" is not a fifth rung — it sends nothing, so the model does
            whatever it would have done. */}
        <SelectItem value={AUTO}>
          <Row label="Auto" blurb={`${dial.dial} ${dial.default_native} · whatever this model does anyway`} />
        </SelectItem>
        {dial.levels.map((level) => (
          <SelectItem key={level.level} value={level.level}>
            <Row label={level.label} blurb={level.blurb} hint={levelHint(level, dial.dial)} />
          </SelectItem>
        ))}
        {deferred && <Applies text={NEXT_SESSION} />}
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
  const [tier, saveTier] = useStoredPreference("tier", "");
  const chosen = TIERS.find((t) => t.key === tier);
  const Icon = chosen ? TIER_ICONS[chosen.key] : Scale;

  function pick(value) {
    saveTier(value === AUTO ? "" : value);
  }

  return (
    <Select value={tier || AUTO} onValueChange={pick}>
      <SelectTrigger size="sm" className={CHIP} aria-label="Which model tier runs this">
        <Icon className="size-3" aria-hidden />
        <span>Model: {chosen ? chosen.label.toLowerCase() : "auto"}</span>
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="max-w-[320px]">
        <SelectItem value={AUTO}>
          <Row label="Auto" blurb="Duct's pick for the job — Heavy for a brief, Standard for a follow-up" />
        </SelectItem>
        {TIERS.map((t) => (
          <SelectItem key={t.key} value={t.key}>
            <Row label={t.label} blurb={t.tagline} />
          </SelectItem>
        ))}
        <Applies text={deferred ? NEXT_SESSION : "Which model each tier means is set in Settings → Models"} />
      </SelectContent>
    </Select>
  );
}

/** What shape the brief takes. Binds when the agent is built, like thinking
 * and tier, so a running thread keeps the format it opened with. */
export function BriefFormatDial({ deferred = false }) {
  const [format, saveFormat] = useStoredPreference("preferred_artifact_format", DEFAULT_BRIEF_FORMAT);
  const chosen = BRIEF_FORMATS.find((f) => f.value === format) || BRIEF_FORMATS[0];

  return (
    <Select value={format} onValueChange={saveFormat}>
      <SelectTrigger size="sm" className={CHIP} aria-label="What shape the brief takes">
        <chosen.Icon className="size-3" aria-hidden />
        <span>Brief: {chosen.label.toLowerCase()}</span>
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="max-w-[320px]">
        {BRIEF_FORMATS.map((f) => (
          <SelectItem key={f.value} value={f.value}>
            <Row label={f.label} blurb={f.blurb} />
          </SelectItem>
        ))}
        {deferred && <Applies text={NEXT_SESSION} />}
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
      <BriefFormatDial deferred={deferred} />
    </div>
  );
}
