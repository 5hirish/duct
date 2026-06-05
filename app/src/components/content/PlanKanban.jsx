"use client";

import { STATUS_ORDER, statusMeta } from "../../lib/contentStatus";
import { effectiveSchedule, monthStartOf } from "../../lib/contentSchedule";
import PostMiniCard from "./PostMiniCard";

const COLUMNS = STATUS_ORDER.map((key) => {
  const meta = statusMeta(key);
  return { key, label: meta.label, accent: meta.accentClass };
});

/**
 * Kanban view of the monthly plan, columns by status. Cards are rich
 * (PostMiniCard) and each lane is sorted by effective date so you see what's
 * upcoming. Posts link to days by post_id (no day numbering).
 *
 * Props:
 *   - plan: { days[], start_date }
 *   - postsById: { [id]: fullPost }
 *   - onReviseDay?(index)
 */
export default function PlanKanban({ plan, postsById = {}, onReviseDay }) {
  const days = Array.isArray(plan?.days) ? plan.days : [];
  const monthStart = monthStartOf(plan);

  const grouped = Object.fromEntries(COLUMNS.map((c) => [c.key, []]));
  days.forEach((d, idx) => {
    const post = d.post_id ? postsById[d.post_id] || null : null;
    const schedule = effectiveSchedule(d, post, monthStart, idx);
    const status = schedule.status || "pending";
    (grouped[status] = grouped[status] || []).push({ day: d, post, schedule, index: idx });
  });

  // Sort each lane by effective date — posted newest-first, everything else
  // oldest-first (upcoming next). Items without a date sort last.
  for (const col of COLUMNS) {
    const desc = col.key === "posted";
    grouped[col.key].sort((a, b) => {
      const ta = a.schedule.date?.getTime();
      const tb = b.schedule.date?.getTime();
      if (ta == null && tb == null) return 0;
      if (ta == null) return 1;
      if (tb == null) return -1;
      return desc ? tb - ta : ta - tb;
    });
  }

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {COLUMNS.map((col) => {
          const cards = grouped[col.key] || [];
          return (
            <div key={col.key} className={`flex min-w-0 flex-col rounded-lg border ${col.accent}`}>
              <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {col.label}
                </span>
                <span className="text-xs tabular-nums text-muted-foreground">{cards.length}</span>
              </div>
              <div className="min-h-[80px] flex-1 space-y-2 p-2">
                {cards.length === 0 && (
                  <p className="px-1 py-2 text-xs italic text-muted-foreground/60">Nothing here yet.</p>
                )}
                {cards.map((card) => (
                  <PostMiniCard
                    key={card.index}
                    day={card.day}
                    post={card.post}
                    schedule={card.schedule}
                    onRevise={() => onReviseDay?.(card.index)}
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
