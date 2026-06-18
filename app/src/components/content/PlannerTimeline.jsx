"use client";

import { useMemo, useState } from "react";
import { Images, Video, Image as ImageIcon, Clock, ArrowRight, Sparkles, RefreshCw, Settings2, ExternalLink } from "lucide-react";
import PipelineProgress from "../PipelineProgress";
import { ContentStep } from "../../lib/contentEvents";
import { parseDate, dayKey } from "../../lib/contentSchedule";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import PlannerConfigDialog from "./PlannerConfigDialog";

// Loading ladder — the two fixed backend steps plus a virtual synthesis stage.
const PLAN_STAGES = [
  { id: ContentStep.LOAD_PROJECT,    label: "Loading your brand & connected accounts" },
  { id: ContentStep.ENRICHING,       label: "Researching trends & competitors" },
  { id: ContentStep.SYNTHESIZE_PLAN, label: "Strategizing your 7-day plan", virtual: true },
];

const PLAN_LINES = [
  "Reading your audience & pillars…",
  "Reviewing what's worked before…",
  "Scanning current platform trends…",
  "Studying competitors & gaps…",
  "Picking the best times to post…",
  "Sequencing content types into a narrative…",
  "Locking in the next 7 days…",
];

const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon };
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function timeOf(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}
function fmtTime(d) {
  return d ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
}

/**
 * Right-pane viewport for the Content Planner (update_plan) — a vertical
 * agenda of the rolling next 7 days (from start_date). Re-renders on every
 * PLAN_GENERATED event.
 *
 * Props:
 *   - payload: { type:"plan", id, name, start_date, days[], strategy, ... }
 *   - steps, building: drive the loading ladder
 *   - onReviseDay?(dayIndex, planId) — "Draft this post →" handoff
 *   - onRefreshPosts?() — sends /refresh-posts into the chat
 *   - onSendMessage?(text) — used to ask the agent to re-plan after a config change
 *   - projectId — for the config dialog
 */
export default function PlannerTimeline({
  payload, steps = [], building = false, onReviseDay, onRefreshPosts, onSendMessage, projectId,
}) {
  const [configOpen, setConfigOpen] = useState(false);

  const start = useMemo(() => parseDate(payload?.start_date) || new Date(), [payload?.start_date]);

  // Lay each plan day onto one of the 7 rolling days. Prefer its scheduled_at
  // when that date is inside the window; otherwise fall back to its list index
  // (clamped) so a post never disappears — the plan IS the next 7 days.
  const byDayIndex = useMemo(() => {
    const map = new Map();
    const days = Array.isArray(payload?.days) ? payload.days : [];
    const windowKeys = Array.from({ length: 7 }, (_, i) => dayKey(addDays(start, i)));
    days.forEach((day, index) => {
      let di = null;
      const t = timeOf(day?.scheduled_at);
      if (t) {
        const found = windowKeys.indexOf(dayKey(t));
        if (found >= 0) di = found;
      }
      if (di == null) di = Math.min(index, 6);
      if (!map.has(di)) map.set(di, []);
      map.get(di).push({ day, index, time: t });
    });
    for (const arr of map.values()) {
      arr.sort((a, b) => (a.time ? a.time.getTime() : 0) - (b.time ? b.time.getTime() : 0));
    }
    return map;
  }, [payload, start]);

  function handleConfigSaved(cfg) {
    const plats = (cfg.platforms || []).map((p) => platformMeta(p).label).join(", ");
    const geos = (cfg.geographies || []).join(", ");
    onSendMessage?.(
      `I've updated the planner configuration — platforms: ${plats}; ${cfg.posts_per_day} post(s)/day; ` +
      `geographies: ${geos}; primary objective: ${cfg.primary_objective}. ` +
      `Please update the 7-day plan to match the new configuration.`,
    );
  }

  if (!payload || payload.type !== "plan") {
    return (
      <>
        <PipelineProgress
          stages={PLAN_STAGES}
          steps={steps}
          activeId={ContentStep.SYNTHESIZE_PLAN}
          synthesising={building}
          virtualWaitsForPrior
          lines={PLAN_LINES}
          estimate="~3 min"
          buildingLabel="Building your 7-day plan"
          streamingSubtitle="Strategizing the next 7 days…"
          idleSubtitle="Researching trends and strategizing your plan…"
        />
        <PlannerConfigDialog open={configOpen} projectId={projectId} onClose={() => setConfigOpen(false)} onSaved={handleConfigSaved} />
      </>
    );
  }

  const strategy = payload.strategy || {};
  const dates = Array.from({ length: 7 }, (_, i) => addDays(start, i));
  const todayKey = dayKey(new Date());
  const dayCount = Array.isArray(payload.days) ? payload.days.length : 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border/60 px-4 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{payload.name || "Next 7 days"}</p>
          <p className="truncate text-xs text-muted-foreground">
            {strategy.weekly_theme || `${MONTHS[start.getMonth()]} ${start.getDate()} – ${MONTHS[dates[6].getMonth()]} ${dates[6].getDate()} · ${dayCount} posts`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <HeaderButton onClick={() => setConfigOpen(true)} icon={Settings2} label="Config" />
          {onRefreshPosts && <HeaderButton onClick={onRefreshPosts} icon={RefreshCw} label="Refresh posts" />}
        </div>
      </div>

      {(strategy.narrative_arc || strategy.sequencing_rationale) && (
        <div className="shrink-0 border-b border-primary/15 bg-primary/5 px-4 py-2.5">
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" />
            <div className="min-w-0 space-y-1">
              {strategy.narrative_arc && <p className="text-xs leading-relaxed text-foreground/90">{strategy.narrative_arc}</p>}
              {strategy.sequencing_rationale && (
                <p className="text-[11px] leading-relaxed text-muted-foreground">{strategy.sequencing_rationale}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Vertical agenda — one row per rolling day */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {dates.map((date, i) => {
          const entries = byDayIndex.get(i) || [];
          const isToday = dayKey(date) === todayKey;
          return (
            <div key={dayKey(date)} className={`flex gap-3 border-b border-border/40 px-4 py-3 ${isToday ? "bg-primary/[0.03]" : ""}`}>
              <div className="w-12 shrink-0 pt-0.5 text-center">
                <p className={`text-[10px] uppercase tracking-wide ${isToday ? "text-primary" : "text-muted-foreground"}`}>
                  {WEEKDAYS[date.getDay()]}
                </p>
                <p className={`text-lg font-semibold tabular-nums leading-tight ${isToday ? "text-primary" : "text-foreground"}`}>
                  {date.getDate()}
                </p>
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                {entries.length === 0 ? (
                  <p className="py-1.5 text-xs text-muted-foreground/50">Nothing planned</p>
                ) : (
                  entries.map((e) => (
                    <SlotCard key={e.index} day={e.day} time={e.time} onDraft={() => onReviseDay?.(e.index, payload.id)} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>

      <PlannerConfigDialog open={configOpen} projectId={projectId} onClose={() => setConfigOpen(false)} onSaved={handleConfigSaved} />
    </div>
  );
}

function HeaderButton({ onClick, icon: Icon, label }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
    >
      <Icon className="size-3" />
      {label}
    </button>
  );
}

const FUNNEL_BADGE = {
  awareness:     { label: "Awareness", cls: "bg-sky-500/15 text-sky-600 dark:text-sky-400" },
  consideration: { label: "Consideration", cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  conversion:    { label: "Conversion", cls: "bg-green-500/15 text-green-600 dark:text-green-400" },
};

function SlotCard({ day, time, onDraft }) {
  const TypeIcon = TYPE_ICON[day?.post_type] || Images;
  const platforms = Array.isArray(day?.platforms) && day.platforms.length ? day.platforms : ["tiktok"];
  const title = day?.hook || day?.angle || day?.topic || day?.hook_text || "(untitled)";
  const when = fmtTime(time) || day?.best_time_note || "";
  const funnel = FUNNEL_BADGE[(day?.funnel_stage || "").toLowerCase()];

  return (
    <div className="group rounded-lg border border-border/60 bg-card p-2.5 transition-colors hover:border-primary/40">
      <div className="mb-1 flex items-center gap-2">
        {when && (
          <span className="inline-flex items-center gap-1 text-[11px] font-medium tabular-nums text-muted-foreground">
            <Clock className="size-3" />
            {when}
          </span>
        )}
        {funnel && (
          <span className={`rounded-full px-1.5 py-px text-[9px] font-medium uppercase tracking-wide ${funnel.cls}`}>
            {funnel.label}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1">
          {platforms.slice(0, 3).map((p) => (
            <PlatformGlyph key={p} platform={p} className="size-3.5" title={platformMeta(p).label} />
          ))}
          <TypeIcon className="size-3.5 text-muted-foreground" />
        </span>
      </div>

      <p className="text-sm font-medium leading-snug text-foreground">{title}</p>

      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        {day?.pillar && <span>{day.pillar}</span>}
        {day?.objective && <span className="text-muted-foreground/70">· {day.objective}</span>}
      </div>

      {day?.rationale && <p className="mt-1 text-[11px] leading-snug text-muted-foreground/80">{day.rationale}</p>}

      {Array.isArray(day?.evidence) && day.evidence.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {day.evidence.slice(0, 3).map((ev, i) => (
            <a
              key={i}
              href={ev.tiktok_url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex max-w-full items-center gap-1 rounded-full border border-border/60 bg-muted/50 px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              title={`Grounded in a saved discovery — ${ev.tiktok_url}`}
            >
              <ExternalLink className="size-2.5 shrink-0" />
              <span className="truncate">{ev.label || "discovery"}</span>
            </a>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={onDraft}
        className="mt-2 inline-flex items-center gap-0.5 text-[11px] font-medium text-primary opacity-0 transition-opacity hover:underline group-hover:opacity-100"
      >
        Draft this post <ArrowRight className="size-3" />
      </button>
    </div>
  );
}
