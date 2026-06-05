"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Images, Video, Image as ImageIcon } from "lucide-react";
import { STATUS_ORDER, statusMeta } from "../../lib/contentStatus";
import { dayKey, effectiveSchedule, monthStartOf } from "../../lib/contentSchedule";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import PostMiniCard from "./PostMiniCard";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const TYPE_ICON = { slideshow: Images, video: Video, image: ImageIcon };

function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function startOfWeek(d) {
  return addDays(d, -d.getDay());
}
function platformsOf(entry) {
  const p = entry.post?.platforms?.length ? entry.post.platforms : entry.day?.platforms;
  return Array.isArray(p) ? p : [];
}

/**
 * Calendar view of the monthly plan. Items land on their effective date
 * (published > scheduled > proposed slot), so a day can hold several.
 *   - view="month" → compact overview (platform logos + per-type counts)
 *   - view="week"  → time-ordered stacked PostMiniCards per day
 *
 * Props: { plan, postsById, view, onViewChange, onReviseDay }
 */
export default function PlanCalendar({ plan, postsById = {}, view = "month", onViewChange, onReviseDay }) {
  const monthStart = monthStartOf(plan);

  const byDate = useMemo(() => {
    const map = new Map();
    if (!monthStart) return map;
    const days = Array.isArray(plan?.days) ? plan.days : [];
    days.forEach((d, idx) => {
      const post = d.post_id ? postsById[d.post_id] || null : null;
      const schedule = effectiveSchedule(d, post, monthStart, idx);
      if (!schedule.date) return;
      const k = dayKey(schedule.date);
      if (!map.has(k)) map.set(k, []);
      map.get(k).push({ day: d, post, schedule, index: idx });
    });
    // Time-order each day: timeless (proposed) first, then by time.
    for (const arr of map.values()) {
      arr.sort((a, b) =>
        (a.schedule.hasTime ? 1 : 0) - (b.schedule.hasTime ? 1 : 0) ||
        (a.schedule.date.getTime() - b.schedule.date.getTime())
      );
    }
    return map;
  }, [plan, postsById, monthStart]);

  const [monthCursor, setMonthCursor] = useState(() => {
    const base = monthStart || new Date();
    return { year: base.getFullYear(), month: base.getMonth() };
  });
  const [weekStart, setWeekStart] = useState(() => startOfWeek(monthStart || new Date()));

  if (!monthStart) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-center">
        <p className="text-sm text-muted-foreground">
          This plan has no start date, so it can&apos;t be placed on a calendar yet.
        </p>
      </div>
    );
  }

  const openWeek = (date) => {
    setWeekStart(startOfWeek(date));
    onViewChange?.("week");
  };

  return view === "week"
    ? <WeekView byDate={byDate} weekStart={weekStart} setWeekStart={setWeekStart} onReviseDay={onReviseDay} />
    : <MonthView byDate={byDate} cursor={monthCursor} setCursor={setMonthCursor} onOpenWeek={openWeek} />;
}

// ---------------------------------------------------------------------------
// Legend + month nav (shared header bits)
// ---------------------------------------------------------------------------

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {STATUS_ORDER.map((s) => {
        const meta = statusMeta(s);
        return (
          <span key={s} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={`size-2 rounded-full ${meta.dotClass}`} />
            {meta.label}
          </span>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Month view — compact overview
// ---------------------------------------------------------------------------

function MonthView({ byDate, cursor, setCursor, onOpenWeek }) {
  const firstOfMonth = new Date(cursor.year, cursor.month, 1);
  const gridStart = startOfWeek(firstOfMonth);
  const cells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
  const todayKey = dayKey(new Date());

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <button type="button" aria-label="Previous month"
            onClick={() => setCursor((c) => { const d = new Date(c.year, c.month - 1, 1); return { year: d.getFullYear(), month: d.getMonth() }; })}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <ChevronLeft className="size-4" />
          </button>
          <h2 className="min-w-[9rem] text-center text-base font-semibold tabular-nums">{MONTHS[cursor.month]} {cursor.year}</h2>
          <button type="button" aria-label="Next month"
            onClick={() => setCursor((c) => { const d = new Date(c.year, c.month + 1, 1); return { year: d.getFullYear(), month: d.getMonth() }; })}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <ChevronRight className="size-4" />
          </button>
        </div>
        <Legend />
      </div>

      <div className="mb-2 grid grid-cols-7 gap-2">
        {WEEKDAYS.map((w) => (
          <div key={w} className="px-1 text-xs font-medium text-muted-foreground">{w}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-2">
        {cells.map((date) => {
          const key = dayKey(date);
          const entries = byDate.get(key) || [];
          return (
            <MonthCell
              key={key}
              date={date}
              inMonth={date.getMonth() === cursor.month}
              isToday={key === todayKey}
              entries={entries}
              onOpenWeek={onOpenWeek}
            />
          );
        })}
      </div>
    </div>
  );
}

function MonthCell({ date, inMonth, isToday, entries, onOpenWeek }) {
  // unique platforms + per-type counts across the day
  const platforms = [...new Set(entries.flatMap(platformsOf))];
  const typeCounts = entries.reduce((acc, e) => {
    const t = e.post?.post_type || e.day?.post_type || "slideshow";
    acc[t] = (acc[t] || 0) + 1;
    return acc;
  }, {});

  return (
    <button
      type="button"
      onClick={() => entries.length && onOpenWeek(date)}
      className={`flex min-h-24 flex-col rounded-lg border p-2 text-left transition-colors ${
        isToday ? "border-primary/60 bg-primary/5" : "border-border/60"
      } ${inMonth ? "bg-background" : "bg-muted/20"} ${entries.length ? "hover:border-primary/50 cursor-pointer" : "cursor-default"}`}
    >
      <div className="flex items-start justify-between">
        <span className={`text-xs font-medium tabular-nums ${inMonth ? "text-foreground" : "text-muted-foreground/50"}`}>
          {date.getDate()}
        </span>
        {platforms.length > 0 && (
          <span className="flex items-center gap-0.5">
            {platforms.slice(0, 3).map((p) => {
              const meta = platformMeta(p);
              return (
                <span key={p} title={meta.label}
                  className="flex size-3.5 items-center justify-center rounded-sm text-white"
                  style={{ backgroundColor: meta.color }}>
                  <PlatformGlyph platform={p} className="size-2" />
                </span>
              );
            })}
            {platforms.length > 3 && <span className="text-[9px] text-muted-foreground">+{platforms.length - 3}</span>}
          </span>
        )}
      </div>

      {entries.length > 0 && (
        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
          {Object.entries(typeCounts).map(([t, n]) => {
            const Icon = TYPE_ICON[t] || Images;
            return (
              <span key={t} className="inline-flex items-center gap-0.5 rounded bg-muted px-1 py-px text-[10px] text-muted-foreground">
                <Icon className="size-2.5" /> {n}
              </span>
            );
          })}
        </div>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Week view — time-ordered stacked cards per day
// ---------------------------------------------------------------------------

function WeekView({ byDate, weekStart, setWeekStart, onReviseDay }) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const todayKey = dayKey(new Date());
  const end = addDays(weekStart, 6);
  const range = `${MONTHS[weekStart.getMonth()].slice(0, 3)} ${weekStart.getDate()} – ${MONTHS[end.getMonth()].slice(0, 3)} ${end.getDate()}`;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 p-4">
        <div className="flex items-center gap-2">
          <button type="button" aria-label="Previous week"
            onClick={() => setWeekStart((w) => addDays(w, -7))}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <ChevronLeft className="size-4" />
          </button>
          <h2 className="min-w-[10rem] text-center text-base font-semibold tabular-nums">{range}</h2>
          <button type="button" aria-label="Next week"
            onClick={() => setWeekStart((w) => addDays(w, 7))}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <ChevronRight className="size-4" />
          </button>
        </div>
        <Legend />
      </div>

      <div className="grid flex-1 grid-cols-7 gap-px overflow-auto bg-border/40">
        {days.map((date) => {
          const key = dayKey(date);
          const entries = byDate.get(key) || [];
          const isToday = key === todayKey;
          return (
            <div key={key} className="flex min-w-0 flex-col bg-background">
              <div className={`sticky top-0 z-10 border-b border-border/60 bg-background/95 px-2 py-1.5 text-center backdrop-blur ${isToday ? "text-primary" : ""}`}>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{WEEKDAYS[date.getDay()]}</p>
                <p className={`text-sm font-semibold tabular-nums ${isToday ? "text-primary" : ""}`}>{date.getDate()}</p>
              </div>
              <div className="flex-1 space-y-2 p-1.5">
                {entries.map((e) => (
                  <PostMiniCard
                    key={e.index}
                    day={e.day}
                    post={e.post}
                    schedule={e.schedule}
                    showThumb={false}
                    onRevise={() => onReviseDay?.(e.index)}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
