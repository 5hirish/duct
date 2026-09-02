"use client";

// The composer. One chip of context, one box, two controls.
//
// It shows the PROJECT and nothing else. Making someone declare which sources
// and which dates to consider is the wizard we deleted, in miniature: working
// that out is the agent's job, and the headline above reports what it decided.
//
// The two controls are the two real dials — how freely Duct may act, and how
// hard the model thinks. Both are persisted settings, not per-message
// decoration: the posture writes to the project, the thinking level to your
// preferences.
//
// The thinking picker is server-driven. Every provider sells this dial under a
// different name with a different ladder, so Duct names four rungs and
// backend/agents/thinking.py maps them per model. The menu shows the resolved
// native value under each rung, which is the honesty clause: the abstraction
// saves you from learning five dialects, it does not hide which one is in use.
// A model with no dial (Gemini 2.5, Haiku 4.5, gpt-4o) shows no control.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CornerDownLeft, Sparkles } from "lucide-react";
import {
  Select, SelectContent, SelectItem, SelectTrigger,
} from "@/components/ui/select";
import { faviconUrl } from "@/lib/favicon";
import { AUTONOMY_OPTIONS, setProjectAutonomy } from "@/lib/projectsApi";
import { loadPreferences, savePreferences } from "@/lib/userPreferences";
import { DEFAULT_ENGINE, ENGINE_STORAGE_KEY } from "@/lib/engines";
import { NO_THINKING, fetchThinking, levelHint } from "@/lib/thinking";
import ContextRing from "./ContextRing";

// Both controls read as chips — the same object as the project chip above the
// box, because they are the same kind of thing: what this message will run with.
// Height comes from the trigger's own size="sm" (h-8) — a bare h-7 here loses
// to the component's data-[size] variant, which is a fight not worth having.
const CHIP =
  "gap-1.5 rounded-full border bg-transparent px-2.5 text-[12px] text-muted-foreground " +
  "shadow-none hover:bg-accent hover:text-foreground focus-visible:ring-0";

// The stored value for "let the model decide" is "", which a Select cannot
// hold — Radix treats an empty string as no selection.
const AUTO = "auto";

export default function DeskComposer({ project, autonomy, onAutonomyChange, placeholder }) {
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(() => loadPreferences().thinking || "");
  // Which rungs exist depends on the model the engine resolves to, so the
  // server answers it. Until it does — or when the model has no dial — the
  // control simply isn't there.
  const [dial, setDial] = useState(NO_THINKING);

  useEffect(() => {
    let alive = true;
    const engine =
      (typeof window !== "undefined" && localStorage.getItem(ENGINE_STORAGE_KEY)) || DEFAULT_ENGINE;
    fetchThinking(engine).then((d) => alive && setDial(d));
    return () => {
      alive = false;
    };
  }, []);

  const website = project?.company?.website_url || "";
  const icon = faviconUrl(website);
  const name = project?.company?.name || project?.name || "This project";

  function send() {
    const q = draft.trim();
    if (!q) return;
    const params = new URLSearchParams({ q });
    if (project?.id) params.set("project", project.id);
    router.push(`/insights/session?${params}`);
  }

  const autonomyLabel =
    AUTONOMY_OPTIONS.find((o) => o.value === autonomy)?.label || "Ask";
  // The chip says the Duct word; the menu says which provider word it becomes.
  const thinkingLabel =
    dial.levels.find((l) => l.level === thinking)?.label.toLowerCase() || "auto";

  function pickThinking(value) {
    const next = value === AUTO ? "" : value;
    setThinking(next);
    savePreferences({ ...loadPreferences(), thinking: next });
  }

  async function pickAutonomy(value) {
    onAutonomyChange(value);
    if (!project?.id) return;
    try {
      await setProjectAutonomy(project.id, value);
    } catch {
      /* the picker is a hint; the backend is the authority on next request */
    }
  }

  return (
    <div className="mx-auto w-full max-w-[720px]">
      <div className="mb-2.5 flex">
        <span className="inline-flex items-center gap-2 rounded-lg border bg-card py-1 pl-[7px] pr-3 text-[12.5px]">
          <span className="flex size-[18px] shrink-0 items-center justify-center overflow-hidden rounded border bg-background">
            {icon ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={icon} alt="" width={14} height={14} className="size-3.5" />
            ) : (
              <span className="size-[7px] rounded-full bg-[var(--orange)]" />
            )}
          </span>
          {name}
        </span>
      </div>

      <div className="rounded-xl border bg-card focus-within:border-ring">
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={placeholder}
          aria-label="Ask Duct"
          className="w-full resize-none bg-transparent px-4 py-3.5 text-[15px] leading-relaxed outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
          <div className="flex items-center gap-1.5">
            <Select value={autonomy} onValueChange={pickAutonomy}>
              <SelectTrigger size="sm" className={CHIP} aria-label="How freely Duct may act">
                <span>{autonomyLabel}</span>
              </SelectTrigger>
              <SelectContent align="start" className="max-w-[320px]">
                {AUTONOMY_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    <span className="flex flex-col items-start gap-0.5">
                      <span>{o.label}</span>
                      <span className="text-[11px] leading-snug text-muted-foreground">
                        {o.blurb}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Absent, not disabled, when the model has no such dial. */}
            {dial.supported && (
              <Select value={thinking || AUTO} onValueChange={pickThinking}>
                <SelectTrigger
                  size="sm"
                  className={CHIP}
                  aria-label="How hard the model should think"
                >
                  <Sparkles className="size-3" aria-hidden />
                  <span>Thinking: {thinkingLabel}</span>
                </SelectTrigger>
                <SelectContent align="start" className="max-w-[320px]">
                  {/* "Auto" is not a fifth rung — it sends nothing, so the model
                      does whatever it would have done. */}
                  <SelectItem value={AUTO}>
                    <span className="flex flex-col items-start gap-0.5">
                      <span>Auto</span>
                      <span className="text-[11px] leading-snug text-muted-foreground">
                        {dial.dial} {dial.default_native} · whatever this model does anyway
                      </span>
                    </span>
                  </SelectItem>
                  {dial.levels.map((level) => (
                    <SelectItem key={level.level} value={level.level}>
                      <span className="flex flex-col items-start gap-0.5">
                        <span>{level.label}</span>
                        <span className="text-[11px] leading-snug text-muted-foreground">
                          {level.blurb}
                        </span>
                        {/* The honesty clause: which provider word this becomes. */}
                        <span className="text-[10.5px] font-mono text-muted-foreground/70">
                          {levelHint(level, dial.dial)}
                        </span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* A new thread starts empty — the ring fills once there is a
                conversation to spend the window on. */}
            <ContextRing used={0} label="New thread" />
            <button
              type="button"
              onClick={send}
              disabled={!draft.trim()}
              aria-label="Send"
              className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-35"
            >
              <CornerDownLeft className="size-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
