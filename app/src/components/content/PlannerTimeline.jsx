"use client";

import { useMemo } from "react";
import { Images, Video, Image as ImageIcon, Clock, ArrowRight, Sparkles, RefreshCw } from "lucide-react";
import PipelineProgress from "../PipelineProgress";
import { ContentStep } from "../../lib/contentEvents";
import { parseDate, dayKey } from "../../lib/contentSchedule";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";

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

function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/**
 * Right-pane viewport for the Content Planner (update_plan) — a fixed 7-day
 * timeline of the canonical plan. Re-renders on every PLAN_GENERATED event.
 *
 * Props:
 *   - payload: { type:"plan", id, name, start_date, days[], strategy, ... }
 *   - steps: live pipeline steps (drives the loading ladder)
 *   - building: still being built (no payload yet, run not failed)
 *   - onReviseDay?(dayIndex) — "Draft this post →" handoff
 */
export default function PlannerTimeline({ payload, steps = [], building = false, onReviseDay, onRefreshPosts }) {
  const start = useMemo(() => {
    const d = parseDate(payload?.start_date);
    return d || new Date();
  }, [payload?.start_date]);

  // Lay each plan day onto a calendar date: its scheduled_at, else start + index.
  const byDate = useMemo(() => {
    const map = new Map();
    const days = Array.isArray(payload?.days) ? payload.days : [];
    days.forEach((day, index) => {
      let date = null;
      if (day?.scheduled_at) {
        const d = new Date(day.scheduled_at);
        if (!Number.isNaN(d.getTime())) date = d;
      }
      if (!date) date = addDays(start, index);
      const k = dayKey(date);
      if (!map.has(k)) map.set(k, []);
      map.get(k).push({ day, index });
    });
    return map;
  }, [payload, start]);

  if (!payload || payload.type !== "plan") {
    return (
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
    );
  }

  const strategy = payload.strategy || {};
  const dates = Array.from({ length: 7 }, (_, i) => addDays(start, i));
  const todayKey = dayKey(new Date());
  const dayCount = Array.isArray(payload.days) ? payload.days.length : 0;

  // Anything the agent scheduled outside the 7-day window would otherwise
  // vanish from the grid — surface it explicitly instead of dropping it.
  const windowKeys = new Set(dates.map(dayKey));
  const overflow = [];
  for (const [k, entries] of byDate.entries()) {
    if (!windowKeys.has(k)) overflow.push(...entries);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-border/60 px-4 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{payload.name || "7-day plan"}</p>
          {strategy.weekly_theme && (
            <p className="truncate text-xs text-muted-foreground">{strategy.weekly_theme}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {onRefreshPosts && (
            <button
              type="button"
              onClick={onRefreshPosts}
              title="Sync all posts + metrics from PostBridge"
              className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <RefreshCw className="size-3" />
              Refresh posts
            </button>
          )}
          <span className="text-xs tabular-nums text-muted-foreground">{dayCount} posts</span>
        </div>
      </div>

      {(strategy.narrative_arc || strategy.sequencing_rationale) && (
        <div className="shrink-0 border-b border-primary/15 bg-primary/5 px-4 py-2.5">
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" />
            <div className="min-w-0 space-y-1">
              {strategy.narrative_arc && (
                <p className="text-xs leading-relaxed text-foreground/90">{strategy.narrative_arc}</p>
              )}
              {strategy.sequencing_rationale && (
                <p className="text-[11px] leading-relaxed text-muted-foreground">{strategy.sequencing_rationale}</p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid flex-1 grid-cols-7 gap-px overflow-auto bg-border/40">
        {dates.map((date) => {
          const key = dayKey(date);
          const entries = byDate.get(key) || [];
          const isToday = key === todayKey;
          return (
            <div key={key} className="flex min-w-0 flex-col bg-background">
              <div
                className={`sticky top-0 z-10 border-b border-border/60 bg-background/95 px-2 py-1.5 text-center backdrop-blur ${
                  isToday ? "text-primary" : ""
                }`}
              >
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{WEEKDAYS[date.getDay()]}</p>
                <p className={`text-sm font-semibold tabular-nums ${isToday ? "text-primary" : ""}`}>{date.getDate()}</p>
              </div>
              <div className="flex-1 space-y-2 p-1.5">
                {entries.length === 0 ? (
                  <p className="px-1 pt-2 text-center text-[10px] text-muted-foreground/50">—</p>
                ) : (
                  entries.map((e) => (
                    <SlotCard key={e.index} day={e.day} onDraft={() => onReviseDay?.(e.index, payload.id)} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>

      {overflow.length > 0 && (
        <div className="shrink-0 border-t border-amber-400/30 bg-amber-500/10 px-3 py-2">
          <p className="mb-1.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
            {overflow.length} post{overflow.length > 1 ? "s" : ""} scheduled outside this week
          </p>
          <div className="flex flex-wrap gap-2">
            {overflow.map((e) => (
              <SlotCard key={e.index} day={e.day} onDraft={() => onReviseDay?.(e.index, payload.id)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SlotCard({ day, onDraft }) {
  const TypeIcon = TYPE_ICON[day?.post_type] || Images;
  const platforms = Array.isArray(day?.platforms) && day.platforms.length ? day.platforms : ["tiktok"];
  const title = day?.angle || day?.topic || day?.hook_text || "(untitled)";
  const time = fmtTime(day?.scheduled_at) || day?.best_time_note || "";

  return (
    <div className="group rounded-lg border border-border/60 bg-card p-2 text-left transition-colors hover:border-primary/40">
      <div className="mb-1 flex items-center justify-between gap-1">
        <div className="flex items-center gap-1">
          {platforms.slice(0, 3).map((p) => (
            <PlatformGlyph key={p} platform={p} className="size-3.5" title={platformMeta(p).label} />
          ))}
        </div>
        <TypeIcon className="size-3.5 shrink-0 text-muted-foreground" />
      </div>

      {time && (
        <div className="mb-1 flex items-center gap-1 text-[10px] text-muted-foreground">
          <Clock className="size-3" />
          <span className="truncate">{time}</span>
        </div>
      )}

      <p className="line-clamp-3 text-xs font-medium leading-snug text-foreground">{title}</p>

      {day?.pillar && (
        <p className="mt-1 truncate text-[10px] uppercase tracking-wide text-muted-foreground">{day.pillar}</p>
      )}

      {day?.rationale && (
        <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-muted-foreground/80">{day.rationale}</p>
      )}

      <button
        type="button"
        onClick={onDraft}
        className="mt-1.5 inline-flex items-center gap-0.5 text-[10px] font-medium text-primary opacity-0 transition-opacity hover:underline group-hover:opacity-100"
      >
        Draft this post <ArrowRight className="size-3" />
      </button>
    </div>
  );
}
