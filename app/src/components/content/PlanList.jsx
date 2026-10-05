"use client";

import { useId, useMemo, useState } from "react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { POST_STATUS_LABELS, PostStatus } from "../../lib/contentEnums";
import { effectiveSchedule, planStartOf } from "../../lib/contentSchedule";
import { formatDate } from "../../lib/format";
import PostMiniCard from "./PostMiniCard";

const ALL = "all";
const NO_POSTS = Object.freeze({});

// Discarded is last and only offered once something is in it, the rule the
// Kanban already followed for its lane.
const FILTERS = [ALL, PostStatus.PENDING, PostStatus.DRAFT, PostStatus.POSTED, PostStatus.DISCARDED];
const FILTER_LABELS = { [ALL]: msg`All`, ...POST_STATUS_LABELS };

// What an empty filter says. Each is true of the filter, not an apology, and
// the pending one is the plan finished rather than the plan missing.
const NONE_LABELS = {
  [PostStatus.PENDING]: msg`Every post in this plan has a draft.`,
  [PostStatus.DRAFT]: msg`No drafts yet. Pick a pending post to start one.`,
  [PostStatus.POSTED]: msg`Nothing from this plan has gone out yet.`,
  [PostStatus.DISCARDED]: msg`Nothing discarded.`,
};

/**
 * The plan as an agenda: every post in date order, grouped by week, with a
 * filter by status. This is the plan workspace's view, because a plan being
 * written is a sequence of days to read through — a status board for thirty
 * posts that all sit in Pending is one full lane and three empty ones.
 *
 * Props:
 *   - plan: { days[], start_date }
 *   - postsById: { [id]: fullPost } — when known, the post's own status and
 *     dates win over the plan's copy (same rule as every plan view)
 *   - onReviseDay?(index) — a pending row opens the draft for that day
 */
export default function PlanList({ plan, postsById = NO_POSTS, onReviseDay }) {
  const { i18n } = useLingui();
  const [filter, setFilter] = useState(ALL);
  const idBase = useId();

  // planStartOf returns a new Date each call, so it is derived inside the
  // memo rather than handed to it as a dependency that never compares equal.
  const { items, anchor } = useMemo(() => {
    const start = planStartOf(plan);
    const days = Array.isArray(plan?.days) ? plan.days : [];
    const rows = days.map((day, index) => {
      const post = day.post_id ? postsById[day.post_id] || null : null;
      const schedule = effectiveSchedule(day, post, start, index, { locale: i18n.locale });
      return { day, post, schedule, index, status: schedule.status || PostStatus.PENDING };
    });
    // Chronological, the plan's own order breaking ties; an undated item
    // keeps its place at the end rather than jumping to the top.
    rows.sort((a, b) => {
      const ta = a.schedule.date?.getTime() ?? Infinity;
      const tb = b.schedule.date?.getTime() ?? Infinity;
      return ta - tb || a.index - b.index;
    });
    return { items: rows, anchor: start };
  }, [plan, postsById, i18n.locale]);

  const counts = useMemo(() => {
    const out = { [ALL]: items.length };
    for (const it of items) out[it.status] = (out[it.status] || 0) + 1;
    return out;
  }, [items]);

  const visible = filter === ALL ? items : items.filter((it) => it.status === filter);
  const weeks = groupByWeek(visible, anchor, (d) => formatDate(d, { withYear: false, locale: i18n.locale }));

  return (
    // @container: this list sits in SplitWorkspace's resizable pane, where
    // the window's width says nothing about the room a row has.
    <div className="@container flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-border/60 px-4 py-2">
        {FILTERS.map((key) => {
          const n = counts[key] || 0;
          if (key === PostStatus.DISCARDED && n === 0) return null;
          const active = filter === key;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(key)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"
              }`}
            >
              {i18n._(FILTER_LABELS[key])} <span className="tabular-nums opacity-70">{n}</span>
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {visible.length === 0 ? (
          <p className="px-2 py-6 text-sm text-muted-foreground">{i18n._(NONE_LABELS[filter])}</p>
        ) : (
          weeks.map(({ key, number, range, items: rows }) => (
            <section key={key} aria-labelledby={`${idBase}-week-${key}`}>
              <h3
                id={`${idBase}-week-${key}`}
                className="sticky top-0 z-10 flex items-baseline gap-2 bg-background px-2 pb-1.5 pt-3 text-2xs font-medium uppercase tracking-wide text-muted-foreground"
              >
                {number != null && <span><Trans>Week {number}</Trans></span>}
                {range && <span className="font-normal normal-case tracking-normal">{range}</span>}
              </h3>
              <ul>
                {rows.map((it) => (
                  <li key={it.index}>
                    <PostMiniCard
                      variant="row"
                      day={it.day}
                      post={it.post}
                      schedule={it.schedule}
                      onRevise={onReviseDay ? () => onReviseDay(it.index) : undefined}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </div>
  );

}

// Calendar days between two local dates. Counted on the dates, not the
// milliseconds: a week that spans a clock change is an hour short or long.
function daysBetween(from, to) {
  const utc = (d) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

/**
 * Weeks count from the plan's first day, not the calendar's Monday: a plan
 * starting on a Thursday is "week 1" until the next Wednesday, which is how
 * the plan was written. A plan with no start date has no weeks to speak of.
 */
function groupByWeek(rows, start, fmt) {
  if (!start) return [{ key: "all", number: null, range: "", items: rows }];
  const groups = new Map();
  for (const it of rows) {
    const d = it.schedule.date;
    const w = d ? Math.max(0, Math.floor(daysBetween(start, d) / 7)) : Infinity;
    if (!groups.has(w)) groups.set(w, []);
    groups.get(w).push(it);
  }
  return [...groups.entries()].map(([w, items]) => {
    if (w === Infinity) return { key: "undated", number: null, range: "", items };
    const from = new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7);
    const to = new Date(from.getFullYear(), from.getMonth(), from.getDate() + 6);
    return { key: String(w), number: w + 1, range: `${fmt(from)} – ${fmt(to)}`, items };
  });
}
