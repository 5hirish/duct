"use client";

// The three cards. One rule decides which one an item is in — see lib/desk.js.
//
// Only the first card is loud. Three equally-weighted cards give the eye
// nowhere to land, and "needs you" is the only one of the three that is ever
// urgent; the other two are things to read, not things to do.

import Link from "next/link";
import { CARD_LIMIT, NEEDS_YOU, FOUND, IN_PROGRESS, relativeTime } from "@/lib/desk";
import { cn } from "@/lib/utils";

const CARDS = [
  {
    key: NEEDS_YOU,
    label: "Needs you",
    dot: "bg-destructive",
    ring: "border-destructive/40",
    empty: "Nothing is waiting on you.",
  },
  {
    key: FOUND,
    label: "What I found",
    dot: "bg-[var(--orange)]",
    ring: "border-border",
    empty: "Nothing checked yet.",
  },
  {
    key: IN_PROGRESS,
    label: "In progress",
    dot: "bg-primary",
    ring: "border-border",
    empty: "Nothing running.",
  },
];

const TONE_CLASS = {
  sure: "text-emerald-600 dark:text-emerald-400",
  partial: "text-amber-600 dark:text-amber-400",
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

function Item({ item }) {
  return (
    <Link
      href={itemHref(item)}
      className="group block rounded-md -mx-2 px-2 py-1.5 transition-colors hover:bg-accent/60"
    >
      <p className="text-[13.5px] font-medium leading-snug">{item.title}</p>
      <p className="mt-1 text-[11.5px] text-muted-foreground">
        <span className={cn(TONE_CLASS[item.tone] || "text-muted-foreground")}>{item.detail}</span>
        {item.at && <span> · {relativeTime(item.at)}</span>}
      </p>
    </Link>
  );
}

export default function DeskCards({ buckets }) {
  const byKey = {
    [NEEDS_YOU]: buckets.needsYou,
    [FOUND]: buckets.found,
    [IN_PROGRESS]: buckets.inProgress,
  };

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {CARDS.map((card) => {
        const items = byKey[card.key] || [];
        const shown = items.slice(0, CARD_LIMIT);
        const rest = items.length - shown.length;
        return (
          <section
            key={card.key}
            className={cn("flex flex-col rounded-xl border bg-card p-5", card.ring)}
            aria-label={card.label}
          >
            <header className="mb-4 flex items-center gap-2.5">
              <span className={cn("size-[7px] rounded-full", card.dot)} aria-hidden />
              <h2 className="text-[13px] font-bold tracking-tight">{card.label}</h2>
              <span className="text-[13px] text-muted-foreground">{items.length || ""}</span>
            </header>

            {shown.length === 0 ? (
              <p className="text-[12.5px] text-muted-foreground">{card.empty}</p>
            ) : (
              <div className="flex flex-col gap-3.5">
                {shown.map((item) => (
                  <Item key={item.id} item={item} />
                ))}
              </div>
            )}

            {rest > 0 && (
              <p className="mt-auto pt-4 text-[11.5px] text-muted-foreground">
                {rest} more not shown
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
