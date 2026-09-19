"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { STATUS_ORDER, statusMeta } from "../../lib/contentStatus";
import { dayKey, effectiveSchedule, monthStartOf, planStartOf } from "../../lib/contentSchedule";
import PostMiniCard from "./PostMiniCard";

function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function startOfWeek(d) {
  return addDays(d, -d.getDay());
}

// Month and weekday names come from Intl in the interface language rather
// than a hand-typed English table, so the calendar never reads half-translated.
const weekdayName = (d, locale) => d.toLocaleDateString(locale, { weekday: "short" });
const monthDay = (d, locale) => d.toLocaleDateString(locale, { month: "long", day: "numeric" });
const monthDayShort = (d, locale) => d.toLocaleDateString(locale, { month: "short", day: "numeric" });

/**
 * Calendar view of the monthly plan. Items land on their effective date
 * (published > scheduled > proposed slot), so a day can hold several.
 *   - view="month" → compact overview (platform logos + per-type counts)
 *   - view="week"  → time-ordered stacked PostMiniCards per day
 *
 * Props: { plan, postsById, view, onViewChange, onReviseDay }
 */
export default function PlanCalendar({ plan, postsById = {}, view = "month", onViewChange, onReviseDay }) {
  const { i18n } = useLingui();
  const locale = i18n.locale;
  const monthStart = monthStartOf(plan);
  const anchor = planStartOf(plan);

  const byDate = useMemo(() => {
    const map = new Map();
    if (!anchor) return map;
    const days = Array.isArray(plan?.days) ? plan.days : [];
    days.forEach((d, idx) => {
      const post = d.post_id ? postsById[d.post_id] || null : null;
      const schedule = effectiveSchedule(d, post, anchor, idx, { locale });
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
  }, [plan, postsById, anchor, locale]);

  const [monthCursor, setMonthCursor] = useState(() => {
    const base = monthStart || new Date();
    return { year: base.getFullYear(), month: base.getMonth() };
  });
  const [weekStart, setWeekStart] = useState(() => startOfWeek(monthStart || new Date()));

  if (!monthStart) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-center">
        <p className="text-sm text-muted-foreground">
          <Trans>This plan has no start date, so it can&apos;t be placed on a calendar yet.</Trans>
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
  const { i18n } = useLingui();
  return (
    <div className="flex flex-wrap items-center gap-3">
      {STATUS_ORDER.map((s) => {
        const meta = statusMeta(s);
        return (
          <span key={s} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={`size-2 rounded-full ${meta.dotClass}`} />
            {i18n._(meta.label)}
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
  const { t, i18n } = useLingui();
  const firstOfMonth = new Date(cursor.year, cursor.month, 1);
  const gridStart = startOfWeek(firstOfMonth);
  const cells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
  const todayKey = dayKey(new Date());
  const monthTitle = firstOfMonth.toLocaleDateString(i18n.locale, { month: "long", year: "numeric" });

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 px-4 pb-3 pt-4">
        <div className="flex items-center gap-2">
          <button type="button" aria-label={t`Previous month`}
            onClick={() => setCursor((c) => { const d = new Date(c.year, c.month - 1, 1); return { year: d.getFullYear(), month: d.getMonth() }; })}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <ChevronLeft className="size-4" />
          </button>
          <h2 className="min-w-[9rem] text-center text-base font-semibold tabular-nums">{monthTitle}</h2>
          <button type="button" aria-label={t`Next month`}
            onClick={() => setCursor((c) => { const d = new Date(c.year, c.month + 1, 1); return { year: d.getFullYear(), month: d.getMonth() }; })}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <ChevronRight className="size-4" />
          </button>
        </div>
        <Legend />
      </div>

      <div className="grid grid-cols-7 border-b border-border/60 px-4">
        {cells.slice(0, 7).map((d) => (
          <div key={d.getDay()} className="pb-2 text-center text-2xs font-semibold uppercase tracking-wide text-muted-foreground">{weekdayName(d, i18n.locale)}</div>
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
  const { t, i18n } = useLingui();
  const MAX = 3;
  const shown = entries.slice(0, MAX);
  const extra = entries.length - shown.length;
  const dayLabel = monthDay(date, i18n.locale);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpenWeek(date)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpenWeek(date); }
      }}
      aria-label={t`Open week of ${dayLabel}`}
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
              : "text-muted-foreground"
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
            <span className="px-1 text-2xs font-medium text-muted-foreground group-hover:text-foreground">
              <Plural value={extra} one="+# more" other="+# more" />
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
  const { t, i18n } = useLingui();
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const todayKey = dayKey(new Date());
  const end = addDays(weekStart, 6);
  const range = `${monthDayShort(weekStart, i18n.locale)} – ${monthDayShort(end, i18n.locale)}`;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 p-4">
        <div className="flex items-center gap-2">
          <button type="button" aria-label={t`Previous week`}
            onClick={() => setWeekStart((w) => addDays(w, -7))}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <ChevronLeft className="size-4" />
          </button>
          <h2 className="min-w-[10rem] text-center text-base font-semibold tabular-nums">{range}</h2>
          <button type="button" aria-label={t`Next week`}
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
                <p className="text-2xs uppercase tracking-wide text-muted-foreground">{weekdayName(date, i18n.locale)}</p>
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
