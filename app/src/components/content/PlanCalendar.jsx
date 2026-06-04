"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { STATUS_ORDER, statusMeta } from "../../lib/contentStatus";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function pad(n) {
  return String(n).padStart(2, "0");
}

function ymd(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// Parse a "YYYY-MM-DD" date string to a local Date at midnight (avoids the UTC
// shift you'd get from new Date("YYYY-MM-DD")).
function parseISODate(s) {
  if (typeof s !== "string") return null;
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function addDays(date, n) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

/**
 * Monthly calendar view of a 30-day plan.
 * Each plan day lands on start_date + (day - 1); cells show a "Day N" chip and
 * a status-colored dot. Cells with a linked post navigate to the editor.
 *
 * Props:
 *   - plan: { days[], posts[], start_date }
 *   - onReviseDay?(dayIndex)
 */
export default function PlanCalendar({ plan, onReviseDay }) {
  const startDate = useMemo(() => parseISODate(plan?.start_date), [plan?.start_date]);
  const [cursor, setCursor] = useState(() => {
    const base = parseISODate(plan?.start_date) || new Date();
    return { year: base.getFullYear(), month: base.getMonth() };
  });

  // Map date-key → { dayIndex, status, post } for fast cell lookup.
  const byDate = useMemo(() => {
    const map = new Map();
    if (!startDate) return map;
    const days = Array.isArray(plan?.days) ? plan.days : [];
    const postsByDay = new Map();
    for (const post of plan?.posts || []) {
      if (typeof post.day_index === "number") postsByDay.set(post.day_index, post);
    }
    days.forEach((d, idx) => {
      const dayIndex = typeof d.day === "number" ? d.day : idx + 1;
      const date = addDays(startDate, dayIndex - 1);
      map.set(ymd(date), {
        dayIndex,
        status: d.status || "pending",
        topic: d.topic,
        post: postsByDay.get(dayIndex - 1) || postsByDay.get(dayIndex) || null,
      });
    });
    return map;
  }, [plan, startDate]);

  if (!startDate) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center">
        <p className="text-sm text-muted-foreground">
          This plan has no start date, so it can&apos;t be placed on a calendar yet.
          Switch to the Kanban view, or set a start date when generating the plan.
        </p>
      </div>
    );
  }

  // Build a 6-week (42-cell) grid starting on the Sunday on/before the 1st.
  const firstOfMonth = new Date(cursor.year, cursor.month, 1);
  const gridStart = addDays(firstOfMonth, -firstOfMonth.getDay());
  const cells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
  const todayKey = ymd(new Date());

  return (
    <div className="flex-1 overflow-auto p-4">
      {/* Header: month nav + legend */}
      <div className="mb-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="Previous month"
            onClick={() =>
              setCursor((c) => {
                const d = new Date(c.year, c.month - 1, 1);
                return { year: d.getFullYear(), month: d.getMonth() };
              })
            }
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <ChevronLeft className="size-4" />
          </button>
          <h2 className="text-base font-semibold tabular-nums min-w-[9rem] text-center">
            {MONTHS[cursor.month]} {cursor.year}
          </h2>
          <button
            type="button"
            aria-label="Next month"
            onClick={() =>
              setCursor((c) => {
                const d = new Date(c.year, c.month + 1, 1);
                return { year: d.getFullYear(), month: d.getMonth() };
              })
            }
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
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
      </div>

      {/* Weekday header */}
      <div className="grid grid-cols-7 gap-2 mb-2">
        {WEEKDAYS.map((w) => (
          <div key={w} className="text-xs font-medium text-muted-foreground px-1">
            {w}
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-2">
        {cells.map((date) => {
          const key = ymd(date);
          const inMonth = date.getMonth() === cursor.month;
          const isToday = key === todayKey;
          const entry = byDate.get(key);
          return (
            <CalendarCell
              key={key}
              date={date}
              inMonth={inMonth}
              isToday={isToday}
              entry={entry}
              onRevise={onReviseDay}
            />
          );
        })}
      </div>
    </div>
  );
}

function CalendarCell({ date, inMonth, isToday, entry, onRevise }) {
  const meta = entry ? statusMeta(entry.status) : null;
  const postId = entry?.post?.id || null;

  const body = (
    <div
      className={`flex h-full min-h-24 flex-col rounded-lg border p-2 transition-colors ${
        isToday ? "border-primary/60 bg-primary/5" : "border-border/60"
      } ${inMonth ? "bg-background" : "bg-muted/20"} ${
        entry ? "hover:border-primary/50" : ""
      }`}
    >
      <span
        className={`text-xs font-medium tabular-nums ${
          inMonth ? "text-foreground" : "text-muted-foreground/50"
        }`}
      >
        {date.getDate()}
      </span>
      {entry && (
        <div className="mt-1 space-y-1">
          <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${meta.textClass}`}>
            <span className={`size-1.5 rounded-full ${meta.dotClass}`} />
            Day {entry.dayIndex}
          </span>
          {entry.topic && (
            <p className="text-[11px] leading-snug text-muted-foreground line-clamp-2">
              {entry.topic}
            </p>
          )}
        </div>
      )}
    </div>
  );

  if (entry && postId) {
    return <Link href={`/content/posts/${postId}`}>{body}</Link>;
  }
  if (entry && onRevise) {
    return (
      <button type="button" onClick={() => onRevise(entry.dayIndex)} className="text-left">
        {body}
      </button>
    );
  }
  return body;
}
