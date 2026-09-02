"use client";

// The right rail: everything that happened, in time order.
//
// Drawn like a commit log — one continuous line, a ring per entry — because
// that is what it is: an append-only record where the shape of the run matters
// as much as any single row. Times are relative; on a page you open once a day,
// "18 minutes ago" is the useful half of "08:42".

import { History } from "lucide-react";
import { relativeTime } from "@/lib/desk";
import { cn } from "@/lib/utils";

// Colour marks the exception, never the routine.
function ringClass(entry) {
  const action = (entry.action || "").toLowerCase();
  if (action.includes("fail") || action.includes("reject") || action.includes("rolled"))
    return "border-destructive";
  if (action.includes("appl") || action.includes("connect")) return "border-emerald-500";
  if (entry.source === "agent" || entry.source === "auto") return "border-primary";
  return "border-muted-foreground/40";
}

/** Sentence-case a snake_case action for people who did not write the enum. */
function actionLabel(entry) {
  if (entry.summary) return entry.summary;
  const words = `${entry.category} ${entry.action}`.replace(/[_.]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export default function DeskActivity({ items }) {
  return (
    <aside className="min-w-0">
      <h2 className="mb-5 flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.02em] text-muted-foreground">
        <History className="size-3.5" aria-hidden />
        Activity
      </h2>

      {items.length === 0 ? (
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          Nothing yet. Every sync, check and change lands here — with what it found and how to
          undo it.
        </p>
      ) : (
        <div className="relative pl-[22px]">
          <div
            className="absolute bottom-2 left-1 top-1.5 w-px bg-border"
            aria-hidden
          />
          {items.map((entry) => (
            <div key={entry.id} className="relative pb-5 last:pb-0">
              <span
                className={cn(
                  "absolute -left-[22px] top-1 size-[9px] rounded-full border-[1.5px] bg-background",
                  ringClass(entry)
                )}
                aria-hidden
              />
              <p className="text-[12.5px] leading-snug">{actionLabel(entry)}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {relativeTime(entry.created_at)}
                {entry.source === "auto" && " · ran on its own"}
                {entry.source === "agent" && " · Duct"}
              </p>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
