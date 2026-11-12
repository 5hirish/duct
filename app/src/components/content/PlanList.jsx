"use client";

import { useId, useMemo, useState } from "react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { ChevronDown } from "lucide-react";
import { POST_STATUS_LABELS, PostStatus } from "../../lib/contentEnums";
import { AgendaGroup, agendaGroups, onChannel, planItems, startOfDay } from "../../lib/contentSchedule";
import { formatDate } from "../../lib/format";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import PostMiniCard from "./PostMiniCard";

const ALL = "all";
const NO_POSTS = Object.freeze({});

// Missed rows shown before "Show all". An ended plan can have thirty, and the
// first few say what the rest are.
const MISSED_SHOWN = 5;

// Discarded is last and only offered once something is in it, the rule the
// Kanban already followed for its lane.
const FILTERS = [ALL, PostStatus.PENDING, PostStatus.DRAFT, PostStatus.POSTED, PostStatus.DISCARDED];
const FILTER_LABELS = { [ALL]: msg`All`, ...POST_STATUS_LABELS };

// What an empty filter says. Each is true of the filter, not an apology, and
// the pending one is the plan finished rather than the plan missing.
const NONE_LABELS = {
  [ALL]: msg`This plan has no posts yet.`,
  [PostStatus.PENDING]: msg`Every post in this plan has a draft.`,
  [PostStatus.DRAFT]: msg`No drafts yet. Pick a pending post to start one.`,
  [PostStatus.POSTED]: msg`Nothing from this plan has gone out yet.`,
  [PostStatus.DISCARDED]: msg`Nothing discarded.`,
};

/**
 * The plan as an agenda, the board's default view: a content plan is about
 * when, so it reads as a schedule. Rows are grouped by what today makes of
 * them (lib/contentSchedule.js `agendaGroups`): the posts whose day passed
 * without a draft first, then this week, next week and the weeks after, and
 * the rest of the past folded away. A filter by status sits above.
 *
 * Props:
 *   - plan: { days[], start_date }
 *   - postsById: { [id]: fullPost } — when known, the post's own status and
 *     dates win over the plan's copy (same rule as every plan view)
 *   - onReviseDay?(index) — a pending row opens the draft for that day
 *   - scroll: "self" (default) scrolls inside its box, for a pane; "page"
 *     lets the page scroll, with week headings pinned under the top bar
 *   - today: the reader's today, for scenes and tests
 */
export default function PlanList({ plan, postsById = NO_POSTS, onReviseDay, scroll = "self", today, channel = null }) {
  const { i18n } = useLingui();
  const [filter, setFilter] = useState(ALL);
  const [allMissed, setAllMissed] = useState(false);
  const [showEarlier, setShowEarlier] = useState(false);
  const idBase = useId();
  const day = today || startOfDay(new Date());
  const dayStamp = day.getTime();

  const items = useMemo(
    () => planItems(plan, postsById, { locale: i18n.locale, today: new Date(dayStamp) }).filter((it) => onChannel(it, channel)),
    [plan, postsById, i18n.locale, dayStamp, channel]
  );

  const counts = useMemo(() => {
    const out = { [ALL]: items.length };
    for (const it of items) out[it.status] = (out[it.status] || 0) + 1;
    return out;
  }, [items]);

  const visible = filter === ALL ? items : items.filter((it) => it.status === filter);
  const groups = agendaGroups(visible, new Date(dayStamp));
  const fmt = (d) => formatDate(d, { withYear: false, locale: i18n.locale });
  const page = scroll === "page";

  return (
    // @container: this list also sits in SplitWorkspace's resizable pane,
    // where the window's width says nothing about the room a row has.
    <div className={cn("@container flex min-w-0 flex-col", !page && "min-h-0 flex-1")}>
      {/* Filters over nothing are four zeros; the line below says it once. */}
      {items.length > 0 && (
        <div className={cn("flex shrink-0 flex-wrap items-center gap-1.5", page ? "pb-2" : "border-b border-border/60 px-4 py-2")}>
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
                // Neutral when chosen: the brand orange is the page's one
                // primary action, and a filter is not that.
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  active ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"
                )}
              >
                {i18n._(FILTER_LABELS[key])} <span className="tabular-nums opacity-70">{n}</span>
              </button>
            );
          })}
        </div>
      )}

      <div className={cn(page ? "pb-2" : "flex-1 overflow-y-auto px-2 pb-4")}>
        {visible.length === 0 ? (
          <p className="px-2 py-6 text-sm text-muted-foreground">{i18n._(NONE_LABELS[filter])}</p>
        ) : (
          groups.map((group) => {
            const headingId = `${idBase}-${group.key}`;
            const missed = group.kind === AgendaGroup.MISSED;
            const earlier = group.kind === AgendaGroup.EARLIER;
            const capped = missed && !allMissed && group.items.length > MISSED_SHOWN;
            const rows = earlier && !showEarlier ? [] : capped ? group.items.slice(0, MISSED_SHOWN) : group.items;
            return (
              <section key={group.key} aria-labelledby={headingId}>
                <h3
                  id={headingId}
                  className={cn(
                    "sticky z-10 flex items-center gap-2 bg-background px-2 pb-1.5 pt-4 text-xs font-medium text-muted-foreground",
                    page ? "top-13" : "top-0"
                  )}
                >
                  <GroupLabel group={group} fmt={fmt} />
                  <span className="tabular-nums">{group.items.length}</span>
                  {earlier && (
                    <Button
                      variant="ghost"
                      size="xs"
                      className="ml-auto"
                      aria-expanded={showEarlier}
                      onClick={() => setShowEarlier((v) => !v)}
                    >
                      {showEarlier ? <Trans>Hide</Trans> : <Trans>Show</Trans>}
                      <ChevronDown className={cn("transition-transform", showEarlier && "rotate-180")} aria-hidden />
                    </Button>
                  )}
                </h3>
                {rows.length > 0 && (
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
                )}
                {capped && (
                  <Button variant="ghost" size="sm" className="ml-1" onClick={() => setAllMissed(true)}>
                    <Plural value={group.items.length} one="Show all #" other="Show all #" />
                  </Button>
                )}
              </section>
            );
          })
        )}
      </div>
    </div>
  );
}

/** A group's name: what today makes of it, then its dates. */
function GroupLabel({ group, fmt }) {
  if (group.kind === AgendaGroup.MISSED) return <span className="text-warning"><Trans>Missed</Trans></span>;
  if (group.kind === AgendaGroup.EARLIER) return <Trans>Earlier</Trans>;
  if (group.kind === AgendaGroup.UNDATED) return <Trans>No date</Trans>;
  const range = `${fmt(group.from)} – ${fmt(group.to)}`;
  if (group.offset === 0) return <span className="text-foreground"><Trans>This week</Trans> <span className="font-normal text-muted-foreground">{range}</span></span>;
  if (group.offset === 1) return <span><Trans>Next week</Trans> <span className="font-normal">{range}</span></span>;
  const from = fmt(group.from);
  return <Trans>Week of {from}</Trans>;
}
