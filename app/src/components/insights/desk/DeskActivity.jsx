"use client";

// The right rail: everything that happened, in time order.
//
// Drawn like a commit log — one continuous line, a ring per entry — because
// that is what it is: an append-only record where the shape of the run matters
// as much as any single row. Times are relative; on a page you open once a day,
// "18 minutes ago" is the useful half of "08:42".

import { History, PanelRightClose, PanelRightOpen } from "lucide-react";
import { relativeTime } from "@/lib/desk";
import { ClampText } from "@/components/ui/clamp-text";
import { cn } from "@/lib/utils";

/** The panel the collapse control owns, named so `aria-controls` can point at it. */
const PANEL_ID = "desk-activity";

/**
 * The desk row's columns, which are the rail's geometry rather than the desk's.
 *
 * Exported because `/preview` renders this rail beside a stand-in column, and a
 * scene that retyped these would be a replica — it would keep passing while the
 * real row changed underneath it. The gutter narrows with the rail: 2.75rem of
 * strip with an 11-unit gap beside it reads as a stray element, not an edge.
 */
export function activityGridClass(collapsed) {
  return collapsed
    ? "gap-x-5 @3xl:grid-cols-[minmax(0,1fr)_2.75rem]"
    : "gap-x-11 @3xl:grid-cols-[minmax(0,1fr)_288px]";
}

// Colour marks the exception, never the routine.
function ringClass(entry) {
  const action = (entry.action || "").toLowerCase();
  if (action.includes("fail") || action.includes("reject") || action.includes("rolled"))
    return "border-destructive";
  if (action.includes("appl") || action.includes("connect")) return "border-success";
  if (entry.source === "agent" || entry.source === "auto") return "border-primary";
  return "border-muted-foreground/40";
}

/** Sentence-case a snake_case action for people who did not write the enum. */
function actionLabel(entry) {
  if (entry.summary) return entry.summary;
  const words = `${entry.category} ${entry.action}`.replace(/[_.]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export default function DeskActivity({ items, collapsed = false, onToggle }) {
  // Collapsing is a split-layout affordance and nothing else. Below @3xl the
  // rail is stacked under the content at full width, where a 2.75rem strip
  // would be neither smaller nor clearer — so the strip and the control are
  // @3xl-only and the stacked rail ignores the preference entirely. Doing it
  // in CSS rather than by reading a breakpoint in JS keeps one DOM for both.
  if (collapsed) {
    return (
      <aside className="min-w-0">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={false}
          aria-controls={PANEL_ID}
          className="sticky top-20 hidden w-11 flex-col items-center gap-2.5 rounded-lg border border-border py-3 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring @3xl:flex"
        >
          <PanelRightOpen className="size-4" aria-hidden />
          <span className="text-2xs font-bold tabular-nums" aria-hidden>
            {items.length}
          </span>
          <span className="rotate-180 text-2xs font-bold uppercase tracking-[0.08em] [writing-mode:vertical-rl]">
            Activity
          </span>
        </button>

        {/* Stacked layout: no split to reclaim, so the rail stays whole. */}
        <div className="@3xl:hidden">
          <ActivityPanel items={items} />
        </div>
      </aside>
    );
  }

  return (
    <aside className="min-w-0">
      <ActivityPanel items={items} onToggle={onToggle} />
    </aside>
  );
}

function ActivityPanel({ items, onToggle }) {
  return (
    <div id={PANEL_ID}>
      <h2 className="mb-5 flex items-center gap-2 text-sm font-bold uppercase tracking-[0.02em] text-muted-foreground">
        <History className="size-3.5" aria-hidden />
        Activity
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            aria-expanded
            aria-controls={PANEL_ID}
            title="Hide activity"
            className="ml-auto hidden rounded-sm p-1 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring @3xl:inline-flex"
          >
            <PanelRightClose className="size-3.5" aria-hidden />
            <span className="sr-only">Hide activity</span>
          </button>
        )}
      </h2>

      {items.length === 0 ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
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
              <ClampText
                as="p"
                text={actionLabel(entry)}
                className="rounded-sm text-xs leading-snug focus-visible:ring-2 focus-visible:ring-ring"
              />
              <p className="mt-0.5 text-2xs text-muted-foreground">
                {relativeTime(entry.created_at)}
                {entry.source === "auto" && " · ran on its own"}
                {entry.source === "agent" && " · Duct"}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
