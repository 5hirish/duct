"use client";

// How much of the model's window a thread has spent.
//
// A donut rather than a number because the useful reading is "how close to the
// edge", not the figure itself. Neutral until it matters, then amber, then red
// — a gauge that is always coloured is a gauge nobody looks at.

import { cn } from "@/lib/utils";

const R = 8;
const CIRCUMFERENCE = 2 * Math.PI * R;

export default function ContextRing({ used = 0, label = "" }) {
  const pct = Math.max(0, Math.min(1, used));
  const tone =
    pct >= 0.9 ? "stroke-destructive"
    : pct >= 0.75 ? "stroke-amber-500"
    : "stroke-primary";

  return (
    <span className="inline-flex items-center gap-2 text-muted-foreground">
      <svg width="17" height="17" viewBox="0 0 20 20" aria-hidden className="shrink-0">
        <circle cx="10" cy="10" r={R} fill="none" strokeWidth="2.5" className="stroke-border" />
        {pct > 0 && (
          <circle
            cx="10"
            cy="10"
            r={R}
            fill="none"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - pct)}
            transform="rotate(-90 10 10)"
            className={cn(tone)}
          />
        )}
      </svg>
      <span className="text-[12.5px]">{label || `${Math.round(pct * 100)}% context`}</span>
    </span>
  );
}
