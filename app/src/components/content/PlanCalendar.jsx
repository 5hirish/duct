"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { STATUS_ORDER, statusMeta } from "../../lib/contentStatus";
import { dayKey, effectiveSchedule, monthStartOf } from "../../lib/contentSchedule";
import PostMiniCard from "./PostMiniCard";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function startOfWeek(d) {
  return addDays(d, -d.getDay());
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
    : <MonthView byDate={byDate} cursor={monthCursor} setCursor={setMonthCursor} onOpenWeek={openWeek} onReviseDay={onReviseDay} />;
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

function MonthView({ byDate, cursor, setCursor, onOpenWeek, onReviseDay }) {
  const firstOfMonth = new Date(cursor.year, cursor.month, 1);
  const gridStart = startOfWeek(firstOfMonth);
  const cells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
  const todayKey = dayKey(new Date());

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 px-4 pb-3 pt-4">
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

      <div className="grid grid-cols-7 border-b border-border/60 px-4">
        {WEEKDAYS.map((w) => (
          <div key={w} className="pb-2 text-center text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{w}</div>
        ))}
      </div>

      <div className="grid flex-1 auto-rows-fr grid-cols-7 gap-px overflow-auto border-t border-border/40 bg-border/40 px-px">
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
              onReviseDay={onReviseDay}
            />
          );
        })}
      </div>
    </div>
  );
}

function MonthCell({ date, inMonth, isToday, entries, onOpenWeek, onReviseDay }) {
  const MAX = 3;
  const shown = entries.slice(0, MAX);
  const extra = entries.length - shown.length;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpenWeek(date)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpenWeek(date); }
      }}
      aria-label={`Open week of ${MONTHS[date.getMonth()]} ${date.getDate()}`}
      className={`group flex min-h-[7.5rem] cursor-pointer flex-col gap-1 p-1.5 outline-none transition-colors hover:bg-muted/40 focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary ${
        inMonth ? "bg-background" : "bg-muted/20"
      } ${isToday ? "ring-1 ring-inset ring-primary/50" : ""}`}
    >
      <span
        className={`flex size-6 shrink-0 items-center justify-center self-start rounded-full text-xs font-semibold tabular-nums transition-colors ${
          isToday
            ? "bg-primary text-primary-foreground"
            : inMonth
              ? "text-foreground group-hover:bg-muted"
              : "text-muted-foreground/40"
        }`}
      >
        {date.getDate()}
      </span>

      {shown.length > 0 && (
        <div className="flex min-h-0 flex-col gap-1">
          {shown.map((e) => (
            <PostMiniCard
              key={e.index}
              variant="chip"
              day={e.day}
              post={e.post}
              schedule={e.schedule}
              onRevise={() => onReviseDay?.(e.index)}
            />
          ))}
          {extra > 0 && (
            <span className="px-1 text-[10px] font-medium text-muted-foreground group-hover:text-foreground">
              +{extra} more
            </span>
          )}
        </div>
      )}
    </div>
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
                    variant="compact"
                    day={e.day}
                    post={e.post}
                    schedule={e.schedule}
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
