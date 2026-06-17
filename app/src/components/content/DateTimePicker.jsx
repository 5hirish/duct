"use client";

import { useMemo, useState } from "react";
import { CalendarClock, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

// --- pure date helpers (no date-fns) ------------------------------------------
const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const sameDay = (a, b) => a && b && startOfDay(a).getTime() === startOfDay(b).getTime();

function parse(value) {
  if (!value) return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

// Emit the local "YYYY-MM-DDTHH:mm" string (same shape the native input gave).
function toLocalString(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function monthGrid(view) {
  const first = new Date(view.getFullYear(), view.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7; // Monday-first
  const start = new Date(first);
  start.setDate(1 - offset);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
}

/**
 * Themed date + time picker (shadcn Popover + Calendar). Replaces the OS-native
 * datetime-local control so it looks right in light/dark mode.
 *
 * Props:
 *   - value   : "YYYY-MM-DDTHH:mm" string | Date
 *   - onChange: (string) => void   — emits the local datetime string
 *   - min     : Date               — earliest selectable day/time
 */
export default function DateTimePicker({ value, onChange, min }) {
  const selected = parse(value);
  const minDate = min instanceof Date ? min : parse(min);
  const [view, setView] = useState(() => selected || minDate || new Date());

  const cells = useMemo(() => monthGrid(view), [view]);
  const timeStr = selected
    ? `${String(selected.getHours()).padStart(2, "0")}:${String(selected.getMinutes()).padStart(2, "0")}`
    : "";

  function commit(next) {
    onChange?.(toLocalString(next));
  }

  function pickDay(day) {
    const next = new Date(day);
    // keep the chosen time (or default to the min time / 09:00)
    const base = selected || minDate;
    next.setHours(base ? base.getHours() : 9, base ? base.getMinutes() : 0, 0, 0);
    if (minDate && next < minDate) { next.setHours(minDate.getHours(), minDate.getMinutes(), 0, 0); }
    commit(next);
  }

  function pickTime(hhmm) {
    if (!hhmm) return;
    const [h, m] = hhmm.split(":").map(Number);
    const next = new Date(selected || view);
    next.setHours(h, m, 0, 0);
    commit(next);
  }

  const triggerLabel = selected
    ? selected.toLocaleString(undefined, {
        weekday: "short", day: "numeric", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      })
    : "Pick a date & time";

  // The time field is bounded only when the selected day is the min day.
  const timeMin = selected && minDate && sameDay(selected, minDate)
    ? `${String(minDate.getHours()).padStart(2, "0")}:${String(minDate.getMinutes()).padStart(2, "0")}`
    : undefined;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" className="w-full justify-start gap-2 font-normal">
          <CalendarClock className="size-4 text-muted-foreground" />
          {triggerLabel}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        {/* Calendar */}
        <div className="p-3">
          <div className="mb-2 flex items-center justify-between px-1">
            <span className="text-sm font-medium">
              {view.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setView(new Date(view.getFullYear(), view.getMonth() - 1, 1))}
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Previous month"
              >
                <ChevronLeft className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => setView(new Date(view.getFullYear(), view.getMonth() + 1, 1))}
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Next month"
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-7 gap-0.5">
            {WEEKDAYS.map((d) => (
              <div key={d} className="flex h-7 items-center justify-center text-[11px] font-medium text-muted-foreground">
                {d}
              </div>
            ))}
            {cells.map((d, i) => {
              const inMonth = d.getMonth() === view.getMonth();
              const disabled = minDate && startOfDay(d) < startOfDay(minDate);
              const isSel = sameDay(d, selected);
              const isToday = sameDay(d, new Date());
              return (
                <button
                  key={i}
                  type="button"
                  disabled={disabled}
                  onClick={() => pickDay(d)}
                  className={cn(
                    "flex size-8 items-center justify-center rounded-md text-sm transition-colors",
                    !inMonth && "text-muted-foreground/40",
                    disabled && "pointer-events-none opacity-30",
                    isSel
                      ? "bg-primary font-medium text-primary-foreground hover:bg-primary/90"
                      : "hover:bg-muted",
                    isToday && !isSel && "border border-primary/50",
                  )}
                >
                  {d.getDate()}
                </button>
              );
            })}
          </div>
        </div>

        {/* Time */}
        <div className="flex items-center gap-2 border-t border-border/60 p-3">
          <Clock className="size-4 shrink-0 text-muted-foreground" />
          <Input
            type="time"
            value={timeStr}
            min={timeMin}
            onChange={(e) => pickTime(e.target.value)}
            className="h-8 [color-scheme:light] dark:[color-scheme:dark]"
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
