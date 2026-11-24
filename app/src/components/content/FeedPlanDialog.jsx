"use client";

import { useId, useRef, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { plural } from "@lingui/core/macro";
import { ArrowRight, CalendarClock, ChevronDown, ChevronRight, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CONNECTOR_NAMES, LOGOS } from "@/components/connections/logos";
import {
  DEFAULT_FEED,
  Disclosure,
  FeedSource,
  HORIZON_OPTIONS,
  LOOK_BACK_OPTIONS,
  MAX_DAYS_OPTIONS,
  SINCE_LAST,
  SOURCE_CODE_HOSTS,
  codeHostOf,
  feedBlocker,
  offeredSources,
} from "@/lib/contentFeed";
import { Cadence } from "@/lib/schedules";
import { DISCLOSURE_HINTS, DISCLOSURE_LABELS, SOURCE_LABELS } from "@/lib/contentFeedLabels";
import { cn } from "@/lib/utils";

// Each code host's mark for its stone, as a file with its own ink. The stone
// is pale in both themes, so a mark drawn in currentColor took the theme's
// text colour and went white on it in dark mode wherever the stylesheet that
// overrode it was late (the desktop dev window keeps one across reloads).
const CODE_HOST_ICONS = { [FeedSource.GITHUB]: "/icons/github.svg" };

// A link's shape, not copy: the same in every language.
const NOTION_LINK_EXAMPLE = "https://www.notion.so/…";

/**
 * The setup sheet for a plan from shipped work (#561): what Duct reads and,
 * behind Options, how far back, how far ahead, how many posts and how much
 * of private code it may talk about. Presentational: `onStart(options)` gets
 * the answers in `lib/contentFeed.js`'s shape, and the caller opens the
 * session.
 *
 * Most people should only press Find stories: the defaults are the answer,
 * so the sheet opens on the sources and a one-line summary of the rest, and
 * the four tuning questions fold behind it. It used to open on a drawing of
 * the window (invented work stones, the heaviest thing on the sheet), a
 * paragraph, five questions and a one-option host picker; the design-sense
 * review of 2026-11-23 took each out.
 *
 * Props: `open`, `onOpenChange`, `onStart(options)`, `onRepeat(options, cadence)`
 * (saves the same answers as a schedule: every Monday, or on each release,
 * #562 and #563; absent hides it),
 * `githubConnected` (false offers the Toolbox instead of source code), `connected`
 * (the preset ids of the person's MCP servers: Linear and Notion appear as
 * sources only when connected, #565), `initial` and `showOptions` for a scene.
 */
export default function FeedPlanDialog({
  open, onOpenChange, onStart, onRepeat, githubConnected = true, connected = [], initial = DEFAULT_FEED,
  showOptions = false,
}) {
  const { t, i18n } = useLingui();
  const [options, setOptions] = useState(() => ({
    ...initial,
    sources: githubConnected ? initial.sources : initial.sources.filter((s) => !SOURCE_CODE_HOSTS.includes(s)),
  }));
  const [tuning, setTuning] = useState(showOptions);
  const set = (key) => (value) => setOptions((o) => ({ ...o, [key]: value }));
  const toggleSource = (source) =>
    setOptions((o) => ({
      ...o,
      sources: o.sources.includes(source) ? o.sources.filter((s) => s !== source) : [...o.sources, source],
    }));
  // Source code is one row whatever hosts the code. With one host its name is
  // a fact in the row; a picker appears only once there is a choice to make.
  const [codeHost, setCodeHost] = useState(() => codeHostOf(initial.sources) || SOURCE_CODE_HOSTS[0]);
  const pickHost = (next) => {
    setOptions((o) => ({ ...o, sources: o.sources.map((s) => (s === codeHost ? next : s)) }));
    setCodeHost(next);
  };
  const codeOn = githubConnected && options.sources.includes(codeHost);
  const hostName = i18n._(CONNECTOR_NAMES[codeHost]);
  const offered = offeredSources(connected);
  const blocker = feedBlocker(options);
  const nothingPicked = blocker !== null;
  const ids = { read: useId(), host: useId(), tune: useId() };
  // The sheet opens on its answer, Find stories, not on the first row: Enter
  // on open should do the thing the defaults are for.
  const submitRef = useRef(null);

  const lookBackLabel = (n) => (n === SINCE_LAST ? t`Since last time` : t`${n} days back`);
  const horizonLabel = (n) => (n === 7 ? t`1 week ahead` : t`2 weeks ahead`);
  const maxDays = options.maxDays;
  const summary = [
    lookBackLabel(options.lookBack),
    horizonLabel(options.horizon),
    plural(maxDays, { one: "Up to # post", other: "Up to # posts" }),
    ...(codeOn ? [i18n._(DISCLOSURE_LABELS[options.disclosure])] : []),
  ].join(" · ");

  function handleSubmit(event) {
    event.preventDefault();
    if (!nothingPicked) onStart?.(options);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-lg"
        aria-describedby={undefined}
        onOpenAutoFocus={(e) => { e.preventDefault(); submitRef.current?.focus({ focusVisible: false }); }}
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-6" noValidate>
          <DialogHeader>
            <DialogTitle><Trans>Plan from your work</Trans></DialogTitle>
          </DialogHeader>

          <div className="flex flex-col gap-2">
            <p id={ids.read} className="text-sm font-medium"><Trans>What to read</Trans></p>
            <Card role="group" aria-labelledby={ids.read} className="gap-0 overflow-hidden p-0">
              {githubConnected ? (
                <SourceRow
                  checked={codeOn}
                  onToggle={() => toggleSource(codeHost)}
                  mark={<img src={CODE_HOST_ICONS[codeHost]} alt="" />}
                  name={t`Source code`}
                  line={t`${hostName} · releases and finished work`}
                />
              ) : (
                <SourceRow
                  missing
                  mark={<img src={CODE_HOST_ICONS[codeHost]} alt="" />}
                  name={t`Source code`}
                  line={(
                    <a className="inline-flex min-h-6 items-center font-medium text-brand hover:underline" href="/connections?connector=github">
                      <Trans>Connect a repository</Trans>
                    </a>
                  )}
                />
              )}
              <SourceRow
                checked={options.sources.includes(FeedSource.DUCT)}
                onToggle={() => toggleSource(FeedSource.DUCT)}
                mark={(
                  <span className="flex items-end gap-px font-display text-lg leading-none font-bold text-foreground">
                    d<span className="mb-0.5 size-1.5 rounded-full bg-primary" />
                  </span>
                )}
                quietMark
                name={i18n._(SOURCE_LABELS[FeedSource.DUCT])}
                line={t`Reports and the changes you approved`}
              />
              <SourceRow
                checked={options.sources.includes(FeedSource.RSS)}
                onToggle={() => toggleSource(FeedSource.RSS)}
                mark={<img src="/icons/rss.svg" alt="" />}
                name={i18n._(SOURCE_LABELS[FeedSource.RSS])}
                line={t`Blog and newsletter posts from your Toolbox`}
              />
              {offered.includes(FeedSource.LINEAR) && (
                <SourceRow
                  checked={options.sources.includes(FeedSource.LINEAR)}
                  onToggle={() => toggleSource(FeedSource.LINEAR)}
                  mark={<img src="/icons/linear.svg" alt="" />}
                  name={i18n._(SOURCE_LABELS[FeedSource.LINEAR])}
                  line={t`Issues finished in that time`}
                />
              )}
              {offered.includes(FeedSource.NOTION) && (
                <SourceRow
                  checked={options.sources.includes(FeedSource.NOTION)}
                  onToggle={() => toggleSource(FeedSource.NOTION)}
                  mark={<img src="/icons/notion.svg" alt="" />}
                  name={i18n._(SOURCE_LABELS[FeedSource.NOTION])}
                  line={t`Dated pages from one database`}
                />
              )}
            </Card>
            {codeOn && SOURCE_CODE_HOSTS.length > 1 && (
              <div className="flex items-center gap-2">
                <span id={ids.host} className="text-xs font-medium"><Trans>Read code from</Trans></span>
                <Select value={codeHost} onValueChange={pickHost}>
                  <SelectTrigger size="sm" aria-labelledby={ids.host}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    {SOURCE_CODE_HOSTS.map((host) => (
                      <SelectItem key={host} value={host}>
                        <span className="feed-host-mark" aria-hidden>{LOGOS[host]}</span>
                        {i18n._(CONNECTOR_NAMES[host])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {options.sources.includes(FeedSource.NOTION) && (
              <div className="flex flex-col gap-1.5">
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
              </div>
            )}
            {blocker === "no_source" && (
              <p className="text-xs text-destructive" role="alert"><Trans>Pick at least one thing to read.</Trans></p>
            )}
            {blocker === "no_notion_database" && (
              // Guidance, not an error: it shows the moment Notion is ticked, before anything was typed.
              <p className="text-xs text-muted-foreground"><Trans>Paste the Notion database to read, or untick Notion.</Trans></p>
            )}
          </div>

          <div className="flex flex-col gap-4">
            <button
              type="button"
              aria-expanded={tuning}
              aria-controls={ids.tune}
              onClick={() => setTuning((v) => !v)}
              className="-mx-2 flex min-h-11 items-center gap-2 rounded-lg px-2 text-left hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", tuning && "rotate-90")} aria-hidden />
              <span className="text-sm font-medium"><Trans>Options</Trans></span>
              <span className="min-w-0 truncate text-xs text-muted-foreground">{summary}</span>
            </button>
            {tuning && (
              <div id={ids.tune} className="flex flex-col gap-5">
                <Choice
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
                  legend={t`Posts, at most`}
                  hint={t`Only on days with no draft yet.`}
                  value={options.maxDays}
                  onChange={set("maxDays")}
                  options={MAX_DAYS_OPTIONS.map((n) => ({ key: n, label: String(n) }))}
                />
                {codeOn && (
                  <Choice
                    legend={t`From private code, mention`}
                    hint={i18n._(DISCLOSURE_HINTS[options.disclosure])}
                    value={options.disclosure}
                    onChange={set("disclosure")}
                    options={Object.values(Disclosure).map((d) => ({ key: d, label: i18n._(DISCLOSURE_LABELS[d]) }))}
                  />
                )}
              </div>
            )}
          </div>

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
                  {codeOn && codeHost === FeedSource.GITHUB && (
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
 * A source to read, as a row you tick: its mark on a stone, the name, one
 * line, the checkbox. The whole row is the label, so it is one target and
 * one tab stop. `missing` draws the row without a checkbox, its line the way
 * to connect it.
 */
function SourceRow({ checked = false, onToggle, mark, quietMark = false, name, line, missing = false }) {
  const id = useId();
  const Row = missing ? "div" : "label";
  return (
    <Row
      {...(missing ? {} : { htmlFor: id })}
      className={cn(
        "flex items-center gap-3 border-t px-4 py-3 first:border-t-0",
        missing ? "text-muted-foreground" : "cursor-pointer hover:bg-muted/40",
      )}
    >
      <span className={cn(quietMark ? "feed-quiet-stone" : "feed-brand-stone", missing && "opacity-50")} aria-hidden>
        {mark}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-medium">{name}</span>
        {line && <span className="text-xs text-muted-foreground">{line}</span>}
      </span>
      {!missing && <Checkbox id={id} checked={checked} onCheckedChange={onToggle} />}
    </Row>
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
