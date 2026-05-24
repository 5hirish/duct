"use client";

import Link from "next/link";
import { PLATFORM_LABELS, POST_STATUS_LABELS, PostStatus } from "../../lib/contentEnums";

const COLUMNS = [
  { key: PostStatus.PENDING,   label: POST_STATUS_LABELS[PostStatus.PENDING],   accent: "border-amber-400/40 bg-amber-50/40 dark:bg-amber-950/10" },
  { key: PostStatus.DRAFT,     label: POST_STATUS_LABELS[PostStatus.DRAFT],     accent: "border-blue-400/40 bg-blue-50/40 dark:bg-blue-950/10" },
  { key: PostStatus.POSTED,    label: POST_STATUS_LABELS[PostStatus.POSTED],    accent: "border-green-400/40 bg-green-50/40 dark:bg-green-950/10" },
  { key: PostStatus.DISCARDED, label: POST_STATUS_LABELS[PostStatus.DISCARDED], accent: "border-muted-foreground/30 bg-muted/40" },
];

/**
 * Kanban view of the 30-day plan, columns by status.
 * Each card carries:
 *   - day index + topic + pillar pill + platforms
 *   - Revise → /content/posts/{postId} (when post_id is set on the day)
 *   - click anywhere → preview modal (TODO — Phase 6)
 *
 * Props:
 *   - plan: { days: [...], posts?: [...] } — payload from /api/content/plans/{id}
 *           OR from the SSE PLAN_GENERATED event.
 *   - onReviseDay?(dayIndex)            — called when card Revise clicked
 *                                         and the day has no post_id yet.
 */
export default function PlanKanban({ plan, onReviseDay }) {
  const days = Array.isArray(plan?.days) ? plan.days : [];

  // Build a quick lookup of posts by day_index → post id, status
  const postsByDay = new Map();
  for (const post of plan?.posts || []) {
    if (typeof post.day_index === "number") postsByDay.set(post.day_index, post);
  }

  const grouped = Object.fromEntries(COLUMNS.map((c) => [c.key, []]));
  days.forEach((d, idx) => {
    const status = d.status || "pending";
    const dayIndex = typeof d.day === "number" ? d.day : idx + 1;
    const post = postsByDay.get(dayIndex - 1) || postsByDay.get(dayIndex) || null;
    grouped[status] = grouped[status] || [];
    grouped[status].push({ ...d, dayIndex, post });
  });

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 min-w-0">
        {COLUMNS.map((col) => {
          const cards = grouped[col.key] || [];
          return (
            <div
              key={col.key}
              className={`flex flex-col rounded-lg border ${col.accent} min-w-0`}
            >
              <div className="flex items-center justify-between px-3 py-2 border-b border-border/50">
                <span className="text-xs uppercase tracking-wide font-medium text-muted-foreground">
                  {col.label}
                </span>
                <span className="text-xs tabular-nums text-muted-foreground">{cards.length}</span>
              </div>
              <div className="flex-1 p-2 space-y-2 min-h-[80px]">
                {cards.length === 0 && (
                  <p className="text-xs text-muted-foreground/60 italic px-1 py-2">
                    Nothing here yet.
                  </p>
                )}
                {cards.map((card) => (
                  <DayCard
                    key={card.dayIndex}
                    card={card}
                    onRevise={() => onReviseDay?.(card.dayIndex)}
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

function DayCard({ card, onRevise }) {
  const postId   = card.post?.id || card.post_id || null;
  const topic    = card.topic    || "(untitled)";
  const pillar   = card.pillar   || "—";
  const postType = card.post_type || "slideshow";
  const platforms = Array.isArray(card.platforms) ? card.platforms : [];

  return (
    <div className="rounded-md border border-border bg-background p-2.5 space-y-1.5 hover:border-primary/40 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground tabular-nums">
          Day {card.dayIndex}
        </span>
        <span className="text-[10px] rounded-full bg-muted px-1.5 py-px text-muted-foreground">
          {postType}
        </span>
      </div>

      <p className="text-sm font-medium leading-snug line-clamp-2">{topic}</p>

      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[10px] rounded-full bg-primary/10 text-primary px-1.5 py-px font-medium">
          {pillar}
        </span>
        {platforms.map((p) => (
          <span key={p} className="text-[10px] rounded-full bg-muted px-1.5 py-px text-muted-foreground">
            {PLATFORM_LABELS[p] || p}
          </span>
        ))}
      </div>

      <div className="pt-1">
        {postId ? (
          <Link
            href={`/content/posts/${postId}`}
            className="text-xs text-primary hover:underline"
          >
            Revise →
          </Link>
        ) : (
          <button
            type="button"
            onClick={onRevise}
            className="text-xs text-primary hover:underline"
          >
            Draft this post →
          </button>
        )}
      </div>
    </div>
  );
}
