"use client";

import { useId, useRef, useState } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { ArrowRight, CalendarClock, Check, ChevronDown, Eye, PackageCheck, Tag, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { GitHubMark } from "@/components/connections/logos";
import {
  DEFAULT_FEED,
  Disclosure,
  FeedSource,
  HORIZON_OPTIONS,
  LOOK_BACK_OPTIONS,
  MAX_DAYS_OPTIONS,
  SINCE_LAST,
  feedBlocker,
  feedRibbon,
  offeredSources,
} from "@/lib/contentFeed";
import { Cadence } from "@/lib/schedules";
import { DISCLOSURE_HINTS, DISCLOSURE_LABELS, SOURCE_LABELS } from "@/lib/contentFeedLabels";
import { cn } from "@/lib/utils";

// A link's shape, not copy: the same in every language.
const NOTION_LINK_EXAMPLE = "https://www.notion.so/…";

const DISCLOSURE_ICONS = {
  [Disclosure.RELEASES]: Tag,
  [Disclosure.SHIPPED]: PackageCheck,
  [Disclosure.EVERYTHING]: Eye,
};

/**
 * The setup sheet for a plan from shipped work (#561): what Duct reads, how
 * far back, how far ahead, how many days it may change, and how much of a
 * private repository it may talk about. Presentational: `onStart(options)`
 * gets the sheet's answers in `lib/contentFeed.js`'s shape, and the caller
 * opens the session.
 *
 * The drawing at the top is the answers, drawn: the days read on the left
 * with the work in them, today, and the days ahead with the ones a story may
 * land on in orange. It replaces the paragraph that used to explain the four
 * questions, and it moves as they are answered, so a choice shows what it
 * does before anything runs. Rare surface, so it can afford the picture.
 *
 * Props: `open`, `onOpenChange`, `onStart(options)`, `onRepeat(options, cadence)`
 * (saves the same answers as a schedule: every Monday, or on each release,
 * #562 and #563; absent hides it),
 * `githubConnected` (false offers the Toolbox instead of GitHub), `connected`
 * (the preset ids of the person's MCP servers: Linear and Notion appear as
 * sources only when connected, #565), `initial` for a scene.
 */
export default function FeedPlanDialog({
  open, onOpenChange, onStart, onRepeat, githubConnected = true, connected = [], initial = DEFAULT_FEED,
}) {
  const { t, i18n } = useLingui();
  const [options, setOptions] = useState(() => ({
    ...initial,
    sources: githubConnected ? initial.sources : initial.sources.filter((s) => s !== FeedSource.GITHUB),
  }));
  const set = (key) => (value) => setOptions((o) => ({ ...o, [key]: value }));
  const toggleSource = (source) =>
    setOptions((o) => ({
      ...o,
      sources: o.sources.includes(source) ? o.sources.filter((s) => s !== source) : [...o.sources, source],
    }));
  const offered = offeredSources(connected);
  const blocker = feedBlocker(options);
  const nothingPicked = blocker !== null;
  // The sheet opens on its answer, Find stories, not on the first tile: a
  // focus ring around GitHub on arrival read as an error, and Enter on open
  // should do the thing the defaults are for.
  const submitRef = useRef(null);

  function handleSubmit(event) {
    event.preventDefault();
    if (!nothingPicked) onStart?.(options);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-xl"
        onOpenAutoFocus={(e) => { e.preventDefault(); submitRef.current?.focus({ focusVisible: false }); }}
      >
        <form onSubmit={handleSubmit} className="@container flex flex-col gap-6" noValidate>
          <DialogHeader>
            <DialogTitle><Trans>Plan from what you shipped</Trans></DialogTitle>
            <DialogDescription>
              <Trans>Duct keeps what a reader would notice and asks which stories to tell. Your plan changes only when you accept.</Trans>
            </DialogDescription>
          </DialogHeader>

          <FeedWindow options={options} />

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-medium"><Trans>Read</Trans></legend>
            <div className="grid gap-2 @md:grid-cols-2">
              <SourceTile
                checked={options.sources.includes(FeedSource.GITHUB)}
                disabled={!githubConnected}
                onToggle={() => toggleSource(FeedSource.GITHUB)}
                mark={<span className="flex size-8 items-center justify-center rounded-lg bg-foreground p-1.5 text-background"><GitHubMark /></span>}
                name={i18n._(SOURCE_LABELS[FeedSource.GITHUB])}
                line={githubConnected
                  ? t`Releases, merged pull requests, changelog edits`
                  : null}
                missing={!githubConnected}
              />
              <SourceTile
                checked={options.sources.includes(FeedSource.DUCT)}
                onToggle={() => toggleSource(FeedSource.DUCT)}
                mark={(
                  <span className="flex size-8 items-end justify-center gap-px rounded-lg bg-muted pb-1.5 font-display text-lg leading-none font-bold">
                    d<span className="mb-0.5 size-1.5 rounded-full bg-primary" />
                  </span>
                )}
                name={i18n._(SOURCE_LABELS[FeedSource.DUCT])}
                line={t`Briefs, approved changes and what they did`}
              />
              <SourceTile
                checked={options.sources.includes(FeedSource.RSS)}
                onToggle={() => toggleSource(FeedSource.RSS)}
                mark={<BrandStone src="/icons/rss.svg" />}
                name={i18n._(SOURCE_LABELS[FeedSource.RSS])}
                line={t`Posts from the feeds you added in the Toolbox`}
              />
              <SourceTile
                checked={options.sources.includes(FeedSource.MILESTONES)}
                onToggle={() => toggleSource(FeedSource.MILESTONES)}
                mark={(
                  <span className="flex size-8 items-center justify-center rounded-lg bg-primary/15 text-brand">
                    <Trophy className="size-4" aria-hidden />
                  </span>
                )}
                name={i18n._(SOURCE_LABELS[FeedSource.MILESTONES])}
                line={t`Round GitHub star counts and your best week in GA4`}
              />
              {offered.includes(FeedSource.LINEAR) && (
                <SourceTile
                  checked={options.sources.includes(FeedSource.LINEAR)}
                  onToggle={() => toggleSource(FeedSource.LINEAR)}
                  mark={<BrandStone src="/icons/linear.svg" />}
                  name={i18n._(SOURCE_LABELS[FeedSource.LINEAR])}
                  line={t`Issues completed in the window`}
                />
              )}
              {offered.includes(FeedSource.NOTION) && (
                <SourceTile
                  checked={options.sources.includes(FeedSource.NOTION)}
                  onToggle={() => toggleSource(FeedSource.NOTION)}
                  mark={<BrandStone src="/icons/notion.svg" />}
                  name={i18n._(SOURCE_LABELS[FeedSource.NOTION])}
                  line={t`Dated pages in one database you pick`}
                />
              )}
            </div>
            {options.sources.includes(FeedSource.NOTION) && (
              <div className="flex flex-col gap-1.5 pt-1">
                <label htmlFor="feed-notion-database" className="text-xs font-medium">
                  <Trans>Notion database link</Trans>
                </label>
                <Input
                  id="feed-notion-database"
                  type="url"
                  inputMode="url"
                  placeholder={NOTION_LINK_EXAMPLE}
                  value={options.notionDatabase || ""}
                  onChange={(e) => set("notionDatabase")(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  <Trans>A changelog or launch notes database. Duct reads its rows once a run, nothing else in the workspace.</Trans>
                </p>
              </div>
            )}
            {blocker === "no_source" && (
              <p className="text-xs text-destructive" role="alert"><Trans>Pick at least one thing to read.</Trans></p>
            )}
            {blocker === "no_notion_database" && (
              // Guidance, not an error: it shows the moment Notion is ticked, before anything was typed.
              <p className="text-xs text-muted-foreground"><Trans>Paste the Notion database to read, or untick Notion.</Trans></p>
            )}
          </fieldset>

          <div className="grid gap-x-6 gap-y-5 @md:grid-cols-2">
            <Choice
              className="@md:col-span-2"
              legend={t`Look back`}
              value={options.lookBack}
              onChange={set("lookBack")}
              options={LOOK_BACK_OPTIONS.map((n) => ({
                key: n,
                label: n === SINCE_LAST ? t`Since last time` : t`${n} days`,
              }))}
            />
            <Choice
              legend={t`Plan ahead`}
              value={options.horizon}
              onChange={set("horizon")}
              options={HORIZON_OPTIONS.map((n) => ({ key: n, label: n === 7 ? t`1 week` : t`2 weeks` }))}
            />
            <Choice
              legend={t`Days it may change`}
              hint={t`Only days with no draft yet.`}
              value={options.maxDays}
              onChange={set("maxDays")}
              options={MAX_DAYS_OPTIONS.map((n) => ({ key: n, label: String(n) }))}
            />
          </div>

          <DisclosurePicker value={options.disclosure} onChange={set("disclosure")} />

          <DialogFooter className="gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange?.(false)}>
              <Trans>Cancel</Trans>
            </Button>
            {onRepeat && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button type="button" variant="outline" disabled={nothingPicked}>
                    <CalendarClock className="size-4" aria-hidden /> <Trans>Repeat</Trans>
                    <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => onRepeat(options, Cadence.WEEKLY)}>
                    <CalendarClock className="size-4" aria-hidden /> <Trans>Every Monday</Trans>
                  </DropdownMenuItem>
                  {githubConnected && options.sources.includes(FeedSource.GITHUB) && (
                    <DropdownMenuItem onSelect={() => onRepeat(options, Cadence.ON_RELEASE)}>
                      <Tag className="size-4" aria-hidden /> <Trans>On each GitHub release</Trans>
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            <Button ref={submitRef} type="submit" disabled={nothingPicked}>
              <Trans>Find stories</Trans> <ArrowRight className="size-4" aria-hidden />
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * The window, drawn: read this far back, today, plan this far ahead. A day of
 * work is a stone in its kind's colour (a fixed scatter: the picture, not the
 * data, which nobody has read yet); a day a story may land on is orange. The
 * stream under the days is the one blue thing, as on every drawing in Duct.
 */
function FeedWindow({ options }) {
  const { t } = useLingui();
  const ribbon = feedRibbon(options);
  const back = options.lookBack;
  const ahead = options.horizon;
  const stories = options.maxDays;
  const readLabel = back === SINCE_LAST ? t`Since last time` : t`${back} days back`;
  const aheadLabel = ahead === 7 ? t`1 week ahead` : t`2 weeks ahead`;
  return (
    <div
      className="flex flex-col gap-2 rounded-xl bg-muted/50 px-4 pt-3 pb-7"
      role="img"
      aria-label={t`${readLabel} to read, ${aheadLabel} to plan`}
    >
      <div className="flex items-baseline justify-between gap-4 text-xs">
        <span className="font-medium">{readLabel}</span>
        <span className="text-right">
          <span className="font-medium">{aheadLabel}</span>
          <span className="text-muted-foreground"> · <Plural value={stories} one="up to # story" other="up to # stories" /></span>
        </span>
      </div>
      <div
        className="feed-ribbon"
        style={{ "--past": `${ribbon.past.length}fr`, "--ahead": `${ribbon.ahead.length}fr` }}
      >
        <div className="feed-ribbon-days feed-ribbon-past">
          {ribbon.past.map((d) => (
            <span
              key={`p-${d.i}`}
              className={cn("feed-ribbon-day", d.work && "feed-kind")}
              data-kind={d.work || undefined}
              data-work={d.work ? "" : undefined}
            />
          ))}
        </div>
        <span className="feed-ribbon-today">
          <span className="absolute top-full left-1/2 mt-1.5 -translate-x-1/2 whitespace-nowrap text-xs text-muted-foreground">
            <Trans>Today</Trans>
          </span>
        </span>
        <div className="feed-ribbon-days">
          {ribbon.ahead.map((d) => (
            <span key={`a-${d.i}`} className="feed-ribbon-day" data-story={d.story ? "" : undefined} />
          ))}
        </div>
      </div>

    </div>
  );
}

/** A vendor's own mark on a pale stone, legible in both themes (as BringAnyTool's). */
function BrandStone({ src }) {
  return (
    <span className="feed-brand-stone" aria-hidden>
      <img src={src} alt="" />
    </span>
  );
}

/** A source to read, as a tile you tick: the mark, the name, one line. */
function SourceTile({ checked, disabled = false, onToggle, mark, name, line, missing = false }) {
  if (missing) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-dashed border-border p-3">
        <span className="opacity-50">{mark}</span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-sm font-medium text-muted-foreground">{name}</span>
          <a className="text-xs font-medium text-brand hover:underline" href="/connections?connector=github">
            <Trans>Connect a repository</Trans>
          </a>
        </div>
      </div>
    );
  }
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        "relative flex items-center gap-3 rounded-xl border p-3 text-left transition-colors",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        checked ? "border-primary bg-primary/5" : "border-border hover:bg-muted/60",
      )}
    >
      {mark}
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-medium">{name}</span>
        {line && <span className="text-xs text-muted-foreground">{line}</span>}
      </span>
      <span
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors",
          checked ? "border-primary bg-primary text-primary-foreground" : "border-border",
        )}
        aria-hidden
      >
        {checked && <Check className="size-3" strokeWidth={3} />}
      </span>
    </button>
  );
}

/** How much of a private repository the posts may talk about: three tiles. */
function DisclosurePicker({ value, onChange }) {
  const { t, i18n } = useLingui();
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <p id={id} className="text-sm font-medium">{t`From a private repository, talk about`}</p>
      <div role="radiogroup" aria-labelledby={id} className="grid grid-cols-3 gap-2">
        {Object.values(Disclosure).map((d) => {
          const Icon = DISCLOSURE_ICONS[d];
          const on = value === d;
          return (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(d)}
              className={cn(
                "flex flex-col items-start gap-2 rounded-xl border p-3 text-left text-xs font-medium transition-colors",
                "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                on ? "border-primary bg-primary/5 text-foreground" : "border-border text-muted-foreground hover:bg-muted/60 hover:text-foreground",
              )}
            >
              <Icon className={cn("size-4", on && "text-brand")} aria-hidden />
              {i18n._(DISCLOSURE_LABELS[d])}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">{i18n._(DISCLOSURE_HINTS[value])}</p>
    </div>
  );
}

/** One question, its answers as a segmented row. */
function Choice({ legend, hint, value, onChange, options, className }) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <p id={id} className="text-sm font-medium">{legend}</p>
      <div role="radiogroup" aria-labelledby={id} className="flex flex-wrap items-center gap-0.5 self-start rounded-lg bg-muted p-0.5">
        {options.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={value === key}
            onClick={() => onChange(key)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              value === key ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
