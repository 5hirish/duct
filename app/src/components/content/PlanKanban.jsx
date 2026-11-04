"use client";

import { useLingui } from "@lingui/react/macro";
import { PostStatus } from "../../lib/contentEnums";
import { STATUS_ORDER, statusMeta } from "../../lib/contentStatus";
import { planItems, startOfDay } from "../../lib/contentSchedule";
import { cn } from "@/lib/utils";
import PostMiniCard from "./PostMiniCard";

const HIDDEN_WHEN_EMPTY = new Set([PostStatus.FAILED, PostStatus.DISCARDED]);

const COLUMNS = STATUS_ORDER.map((key) => {
  const meta = statusMeta(key);
  return { key, label: meta.label, dot: meta.dotClass };
});

/**
 * The plan by status, for production days. The agenda (PlanList) is the
 * board's default; this is the second view.
 *
 * The lanes follow the content rather than the other way round: a fresh plan
 * is thirty posts in one lane, and two full-height tinted panels beside it
 * saying "Nothing here yet" were most of the screen. A lane with nothing in it
 * is its header and nothing else, narrow beside the lanes that have cards.
 *
 * Props:
 *   - plan: { days[], start_date }
 *   - postsById: { [id]: fullPost }
 *   - onReviseDay?(index)
 *   - scroll: "self" (default) scrolls inside its box; "page" lets the page
 *     scroll, lane headers pinned under the top bar
 *   - today: the reader's today, for scenes and tests
 */
export default function PlanKanban({ plan, postsById = {}, onReviseDay, scroll = "self", today }) {
  const { i18n } = useLingui();
  const page = scroll === "page";
  const items = planItems(plan, postsById, { locale: i18n.locale, today: today || startOfDay(new Date()) });

  const grouped = Object.fromEntries(COLUMNS.map((c) => [c.key, []]));
  for (const it of items) (grouped[it.status] = grouped[it.status] || []).push(it);
  // planItems is oldest first, which is right for what is still ahead; what
  // went out reads newest first.
  grouped[PostStatus.POSTED]?.reverse();

  const lanes = COLUMNS.filter((col) => !(HIDDEN_WHEN_EMPTY.has(col.key) && grouped[col.key].length === 0));

  return (
    // @container, not viewport breakpoints: this board renders both full-width
    // on /content and inside SplitWorkspace's user-resizable right pane, where
    // `lg:` would be true at 1024px of WINDOW while the pane itself is 300px.
    <div className={cn("@container min-w-0", !page && "flex-1 overflow-auto p-4")}>
      <div className="flex flex-col gap-4 @4xl:flex-row @4xl:items-start">
        {lanes.map((col) => {
          const cards = grouped[col.key] || [];
          const empty = cards.length === 0;
          return (
            <section
              key={col.key}
              aria-label={i18n._(col.label)}
              className={cn("flex min-w-0 flex-col gap-2", empty ? "@4xl:w-36 @4xl:shrink-0" : "@4xl:flex-1")}
            >
              <h3
                className={cn(
                  "sticky z-10 flex items-center gap-2 bg-background py-1.5 text-xs font-medium text-muted-foreground",
                  page ? "top-13" : "top-0"
                )}
              >
                <span className={cn("size-2 shrink-0 rounded-full", col.dot)} aria-hidden />
                <span className={cn(!empty && "text-foreground")}>{i18n._(col.label)}</span>
                <span className="tabular-nums">{cards.length}</span>
              </h3>
              {cards.map((card) => (
                <PostMiniCard
                  key={card.index}
                  day={card.day}
                  post={card.post}
                  schedule={card.schedule}
                  onRevise={() => onReviseDay?.(card.index)}
                />
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}
