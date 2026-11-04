"use client";

// The desk's items, in fixed slots.
//
// Every title here was written at run time, by a model or by the person, so
// nothing in this file is sized around one: an item is a mark, a verb, a
// headline clamped to its lines, an optional number and an age, and a missing
// part leaves the row the same shape. Which item leads, how many rows show and
// what is filed away is decided in lib/desk.js (`arrangeDesk`), never here.
//
// The mark is the personality: a tinted tile whose glyph says what kind of
// thing this is, or the connector's own logo when the item came from one —
// recognised before it is read (DESIGN.md, "Content awareness").

import { useState } from "react";
import Link from "next/link";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import {
  Activity, Archive, ChartLine, CircleDashed, Eye, Flag, Lightbulb, ListChecks,
  MessageCircleQuestion, RotateCcw, Scale, Target, TrendingDown, TrendingUp, TriangleAlert,
} from "lucide-react";
import { Tooltip, TooltipTrigger } from "@/components/ui/tooltip";
import { ClampTooltipContent, clampClass } from "@/components/ui/clamp-text";
import { Button } from "@/components/ui/button";
import { Card, CardFooter } from "@/components/ui/card";
import { Section } from "@/components/ui/page";
import { LOGOS } from "@/components/connections/logos";
import { formatDelta, formatMeasure } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useRelativeTime } from "./useRelativeTime";

// What each kind of item looks like. Waiting items by what you would do about
// them, findings by what kind of fact they are. Tints stay in their families
// so the desk reads in three colours, not eleven.
const LOOK = {
  answer: { Icon: MessageCircleQuestion, tile: "bg-info/12 text-info" },
  approve: { Icon: ListChecks, tile: "bg-primary/12 text-brand" },
  review: { Icon: TriangleAlert, tile: "bg-warning/15 text-warning" },
  retry: { Icon: RotateCcw, tile: "bg-muted text-muted-foreground" },
  metric: { Icon: ChartLine, tile: "bg-primary/12 text-brand" },
  conclusion: { Icon: Lightbulb, tile: "bg-warning/15 text-warning" },
  goal: { Icon: Target, tile: "bg-success/12 text-success" },
  milestone: { Icon: Flag, tile: "bg-success/12 text-success" },
  decision: { Icon: Scale, tile: "bg-info/12 text-info" },
  status: { Icon: Activity, tile: "bg-info/12 text-info" },
  watch: { Icon: Eye, tile: "bg-muted text-muted-foreground" },
  incident: { Icon: TriangleAlert, tile: "bg-warning/15 text-warning" },
};

// The words for lib/desk.js's codes; it runs under plain Node and carries none.
const VERB = {
  answer: msg`Answer`,
  approve: msg`Approve`,
  review: msg`Review`,
  retry: msg`Retry`,
};

const LEAD_ACTION = {
  answer: msg`Answer`,
  approve: msg`Review changes`,
  review: msg`Look into it`,
  retry: msg`Open and retry`,
};

const UNTITLED = {
  untitled_thread: msg`Untitled thread`,
  untitled_change_set: msg`Untitled change set`,
};

/** Where an item goes when you click it. Each type knows its own home. */
export function itemHref(item) {
  if (item.type === "change_set") return "/execute";
  if (item.conversationId) return `/insights/session?conversation=${item.conversationId}`;
  // A finding written by an unattended run has provenance but no thread. The
  // useful thing to do with it is ask about it, so that is where clicking goes.
  if (item.type === "memory") return `/insights/session?q=${encodeURIComponent(item.title)}`;
  return "/insights/session";
}

function useTitle() {
  const { i18n } = useLingui();
  return (item) => item.title || (UNTITLED[item.titleCode] ? i18n._(UNTITLED[item.titleCode]) : "");
}

/** The tile: a connector's logo when the item came from one, else its kind. */
function ItemMark({ item, size = "sm" }) {
  const box = size === "lg" ? "size-10 rounded-xl [&_img]:size-5 [&_svg]:size-5" : "size-8 rounded-lg [&_img]:size-4 [&_svg]:size-4";
  const logo = item.source && LOGOS[item.source];
  if (logo) {
    return (
      <span className={cn("flex shrink-0 items-center justify-center border bg-background", box)} aria-hidden>
        {logo}
      </span>
    );
  }
  const look = LOOK[item.verb] || LOOK[item.kind] || LOOK.status;
  const { Icon } = look;
  return (
    <span className={cn("flex shrink-0 items-center justify-center", box, look.tile)} aria-hidden>
      <Icon />
    </span>
  );
}

/**
 * The person's words are shown as theirs. A thread is titled with what they
 * typed, typos and all, and quotation marks say so instead of presenting it
 * as Duct's copy. `<q>` takes the reader's language's quote marks.
 */
function TitleText({ item, text }) {
  return item.titleBy === "person" ? <q>{text}</q> : text;
}

/** A stored number and its change. The arrow carries the direction, not the colour. */
function Figure({ figure, className }) {
  const { i18n } = useLingui();
  if (!figure) return null;
  const Arrow = figure.delta > 0 ? TrendingUp : figure.delta < 0 ? TrendingDown : null;
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5 text-xs tabular-nums", className)}>
      <span className="max-w-36 truncate font-medium text-foreground">
        {formatMeasure(figure.value, figure.unit, { locale: i18n.locale })}
      </span>
      {figure.delta != null && (
        <span className="inline-flex items-center gap-0.5 text-muted-foreground">
          {Arrow && <Arrow className="size-3" aria-hidden />}
          {formatDelta(figure.delta, { locale: i18n.locale })}
        </span>
      )}
    </span>
  );
}

function Copies({ n }) {
  if (!n || n < 2) return null;
  return (
    <span className="tabular-nums text-muted-foreground">
      <Trans>×{n}</Trans>
    </span>
  );
}

/**
 * The one item the desk leads with: the most blocked, most important, most
 * recent waiting thing, as `arrangeDesk` scored it.
 */
export function DeskLead({ item }) {
  const { i18n } = useLingui();
  const titleOf = useTitle();
  const ago = useRelativeTime();
  const title = titleOf(item);
  const when = ago(item.at);
  // The second line is the model's own detail, so it gets the same clamp as
  // the title: a body can run to a page.
  const detail = item.detailCode === "failed" ? item.error : item.body;
  return (
    <Card variant="hero" className="gap-5" data-desk="lead">
      <div className="flex min-w-0 items-start gap-4">
        <ItemMark item={item} size="lg" />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="text-xs text-muted-foreground">
            <LeadEyebrow item={item} />
            {when && <span> · {when}</span>}
          </p>
          <Tooltip>
            <TooltipTrigger asChild>
              <h2
                tabIndex={0}
                className={cn(
                  clampClass(2),
                  "cursor-default rounded-sm text-sm font-semibold leading-snug outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
                )}
              >
                <TitleText item={item} text={title} />
              </h2>
            </TooltipTrigger>
            <ClampTooltipContent text={title} />
          </Tooltip>
          {detail && <p className={cn(clampClass(2), "text-sm text-muted-foreground")}>{detail}</p>}
          <Figure figure={item.figure} />
        </div>
      </div>
      <CardFooter>
        <Button asChild size="sm">
          <Link href={itemHref(item)}>{i18n._(LEAD_ACTION[item.verb] || LEAD_ACTION.review)}</Link>
        </Button>
        {item.copies > 1 && (
          <span className="text-xs text-muted-foreground">
            {item.type === "conversation" ? (
              <Plural value={item.copies} one="You asked this # time" other="You asked this # times" />
            ) : (
              <Plural value={item.copies} one="Duct noted this # time" other="Duct noted this # times" />
            )}
          </span>
        )}
      </CardFooter>
    </Card>
  );
}

function LeadEyebrow({ item }) {
  switch (item.detailCode) {
    case "waiting":
      return <Trans>Duct is waiting on your answer</Trans>;
    case "changes_to_approve":
      return <Plural value={item.count ?? 0} one="# change to approve" other="# changes to approve" />;
    case "failed":
      return <Trans>A run stopped on an error</Trans>;
    default:
      return <Trans>A problem Duct found</Trans>;
  }
}

/** One row: mark, verb, headline on one line, number and age on the right. */
function Row({ item, quiet = false, verb = true, note = false }) {
  const { t, i18n } = useLingui();
  const titleOf = useTitle();
  const ago = useRelativeTime();
  const title = titleOf(item);
  const unsure = note && (item.detailCode === "unconfirmed" || item.detailCode === "low");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={itemHref(item)}
          data-desk="row"
          className={cn(
            "grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 outline-none transition-colors hover:bg-accent/50 focus-visible:bg-accent/50",
            quiet && "text-muted-foreground"
          )}
        >
          <ItemMark item={item} />
          <span className="flex min-w-0 items-baseline gap-2">
            {verb && VERB[item.verb] && (
              <span className="shrink-0 text-xs font-medium text-brand">{i18n._(VERB[item.verb])}</span>
            )}
            <span className={cn(clampClass(1), "min-w-0 text-sm")}>
              <TitleText item={item} text={title} />
            </span>
          </span>
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <Figure figure={item.figure} className="hidden @md:inline-flex" />
            {unsure && (
              <CircleDashed className="size-3.5" aria-label={t`Not confirmed yet`} role="img" />
            )}
            <Copies n={item.copies} />
            <span className="tabular-nums">{ago(item.at)}</span>
          </span>
        </Link>
      </TooltipTrigger>
      <ClampTooltipContent text={unsure ? `${title} · ${t`Not confirmed yet`}` : title} />
    </Tooltip>
  );
}

/** Rows inside one card: a list of one kind of thing is rows, not cards. */
function RowList({ items, ...rowProps }) {
  return (
    <Card className="gap-0 divide-y overflow-hidden p-0">
      {items.map((item) => (
        <Row key={item.id} item={item} {...rowProps} />
      ))}
    </Card>
  );
}

/**
 * The waiting items after the lead. Bounded by `arrangeDesk`; the rest are
 * one click away and still never more than the person asked to see.
 */
export function DeskRows({ rows, more, filed, title }) {
  const [showMore, setShowMore] = useState(false);
  const shown = showMore ? [...rows, ...more] : rows;
  return (
    <Section title={title} count={rows.length + more.length}>
      {shown.length > 0 && <RowList items={shown} />}
      {more.length > 0 && (
        <div>
          <Button variant="ghost" size="sm" onClick={() => setShowMore((v) => !v)} aria-expanded={showMore}>
            {showMore ? <Trans>Show fewer</Trans> : <Plural value={more.length} one="Show # more" other="Show # more" />}
          </Button>
        </div>
      )}
      {filed.length > 0 && <DeskFiled items={filed} />}
    </Section>
  );
}

/**
 * Waiting items too old to be news. Filed, not deleted, and counted out loud
 * so the calm is honest: the page says what it put away.
 */
export function DeskFiled({ items }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Archive className="size-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1">
          <Plural
            value={items.length}
            one="Duct filed # older item away."
            other="Duct filed # older items away."
          />
        </span>
        <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? <Trans>Hide</Trans> : <Trans>Show</Trans>}
        </Button>
      </div>
      {open && <RowList items={items} quiet />}
    </div>
  );
}

/** What Duct knows: a few notes, ranked, the rest on the memory page. */
export function DeskNotes({ notes, total, projectId }) {
  return (
    <Section
      title={<Trans>Notes</Trans>}
      count={total}
      actions={
        projectId && total > notes.length ? (
          <Button asChild variant="ghost" size="sm">
            <Link href={`/project/${projectId}/memory`}>
              <Trans>All notes</Trans>
            </Link>
          </Button>
        ) : null
      }
    >
      <RowList items={notes} verb={false} note />
    </Section>
  );
}

/**
 * What Duct is doing, as a count in the header. Work in progress is ambient:
 * it never takes a card, so it can never be the empty box on the page.
 */
export function DeskWorking({ items }) {
  if (!items.length) return null;
  return (
    <Button asChild variant="outline" size="sm">
      <Link href={itemHref(items[0])}>
        <span className="size-2 rounded-full bg-info" aria-hidden />
        <Plural value={items.length} one="Working on # thing" other="Working on # things" />
      </Link>
    </Button>
  );
}
