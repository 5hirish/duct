"use client";

// The three cards. One rule decides which one an item is in — see lib/desk.js.
//
// Only the first card is loud. Three equally-weighted cards give the eye
// nowhere to land, and "needs you" is the only one of the three that is ever
// urgent; the other two are things to read, not things to do.

import Link from "next/link";
import { msg } from "@lingui/core/macro";
import { Plural, useLingui } from "@lingui/react/macro";
import { CARD_LIMIT, NEEDS_YOU, FOUND, IN_PROGRESS } from "@/lib/desk";
import { Tooltip, TooltipTrigger } from "@/components/ui/tooltip";
import { ClampTooltipContent, clampClass } from "@/components/ui/clamp-text";
import { cn } from "@/lib/utils";
import { useRelativeTime } from "./useRelativeTime";

const CARDS = [
  {
    key: NEEDS_YOU,
    label: msg`Needs you`,
    dot: "bg-destructive",
    ring: "border-destructive/40",
    empty: msg`Nothing is waiting on you.`,
  },
  {
    key: FOUND,
    label: msg`What I found`,
    dot: "bg-[var(--orange)]",
    ring: "border-border",
    empty: msg`Nothing checked yet.`,
  },
  {
    key: IN_PROGRESS,
    label: msg`In progress`,
    dot: "bg-primary",
    ring: "border-border",
    empty: msg`Nothing running.`,
  },
];

// The words for lib/desk.js's codes. The rule lives there and cannot carry
// copy (it runs under plain node, no macro pass); the sentences live here.
const TITLE = {
  untitled_thread: msg`Untitled thread`,
  untitled_change_set: msg`Untitled change set`,
};

const DETAIL = {
  // certainty(): a finding, and how far Duct trusts it
  unconfirmed: msg`Not confirmed`,
  checked: msg`Checked`,
  low: msg`Low confidence`,
  fair: msg`Fairly sure`,
  // an incident nobody has resolved
  unclosed: msg`Nobody has closed this`,
  // a change set past the approval click
  applying: msg`Applying now`,
  approved: msg`Approved, waiting to run`,
  // conversationCard(): a thread, by its run status
  waiting: msg`Waiting on your answer`,
  failed: msg`The last turn failed`,
  working: msg`Working`,
  stopped: msg`Stopped — pick up where it left off`,
  resume: msg`Pick up where you left off`,
};

const TONE_CLASS = {
  sure: "text-success",
  partial: "text-warning",
  unsure: "text-muted-foreground",
  alert: "text-muted-foreground",
  running: "text-muted-foreground",
};

/** Where an item goes when you click it. Each type knows its own home. */
export function itemHref(item) {
  if (item.type === "change_set") return "/execute";
  if (item.conversationId) return `/insights/session?conversation=${item.conversationId}`;
  // A finding written by an unattended run has provenance but no thread. The
  // useful thing to do with it is ask about it, so that is where clicking goes.
  if (item.type === "memory") {
    return `/insights/session?q=${encodeURIComponent(item.title)}`;
  }
  return "/insights/session";
}

// A finding's title can run to a full sentence (an agent wrote it, not a
// human picking a label). Two lines, with the rest on hover/focus — the
// trigger is the row itself, not a second focusable span, so tabbing the
// card still lands on one stop per item (AGENTS.md accessibility rule).
function Item({ item }) {
  const { i18n } = useLingui();
  const relative = useRelativeTime();
  const title = item.title || (TITLE[item.titleCode] ? i18n._(TITLE[item.titleCode]) : "");
  const count = item.count ?? 0;
  const detail =
    item.detailCode === "changes_to_approve" ? (
      <Plural value={count} one="# change to approve" other="# changes to approve" />
    ) : item.detailCode === "failed" && item.error ? (
      // The backend's own reason for the failure, when it gave one.
      item.error
    ) : DETAIL[item.detailCode] ? (
      i18n._(DETAIL[item.detailCode])
    ) : (
      ""
    );
  const ago = relative(item.at);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={itemHref(item)}
          className="group block rounded-md -mx-2 px-2 py-1.5 transition-colors hover:bg-accent/60"
        >
          <p className={cn(clampClass(2), "text-sm font-medium leading-snug")}>{title}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            <span className={cn(TONE_CLASS[item.tone] || "text-muted-foreground")}>{detail}</span>
            {ago && <span> · {ago}</span>}
          </p>
        </Link>
      </TooltipTrigger>
      <ClampTooltipContent text={title} />
    </Tooltip>
  );
}

export default function DeskCards({ buckets }) {
  const { i18n } = useLingui();
  const byKey = {
    [NEEDS_YOU]: buckets.needsYou,
    [FOUND]: buckets.found,
    [IN_PROGRESS]: buckets.inProgress,
  };

  return (
    <div className="grid gap-4 @lg:grid-cols-2 @3xl:grid-cols-3">
      {CARDS.map((card) => {
        const items = byKey[card.key] || [];
        const shown = items.slice(0, CARD_LIMIT);
        const rest = items.length - shown.length;
        return (
          <section
            key={card.key}
            className={cn("flex flex-col rounded-xl border bg-card p-5", card.ring)}
            aria-label={i18n._(card.label)}
          >
            <header className="mb-4 flex items-center gap-2.5">
              <span className={cn("size-[7px] rounded-full", card.dot)} aria-hidden />
              <h2 className="text-sm font-bold tracking-tight">{i18n._(card.label)}</h2>
              <span className="text-sm text-muted-foreground">{items.length || ""}</span>
            </header>

            {shown.length === 0 ? (
              <p className="text-xs text-muted-foreground">{i18n._(card.empty)}</p>
            ) : (
              <div className="flex flex-col gap-3.5">
                {shown.map((item) => (
                  <Item key={item.id} item={item} />
                ))}
              </div>
            )}

            {rest > 0 && (
              <p className="mt-auto pt-4 text-xs text-muted-foreground">
                <Plural value={rest} one="# more not shown" other="# more not shown" />
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
