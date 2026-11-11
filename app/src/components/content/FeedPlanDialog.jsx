"use client";

import { useId, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  DEFAULT_FEED,
  Disclosure,
  FeedSource,
  HORIZON_OPTIONS,
  LOOK_BACK_OPTIONS,
  MAX_DAYS_OPTIONS,
  SINCE_LAST,
} from "@/lib/contentFeed";
import { DISCLOSURE_HINTS, DISCLOSURE_LABELS, SOURCE_LABELS } from "@/lib/contentFeedLabels";
import { cn } from "@/lib/utils";

/**
 * The setup sheet for a plan from shipped work (#561): what Duct reads, how
 * far back, how far ahead, how many days it may change, and how much of a
 * private repository it may talk about. Presentational: `onStart(options)`
 * gets the sheet's answers in `lib/contentFeed.js`'s shape, and the caller
 * opens the session.
 *
 * Props: `open`, `onOpenChange`, `onStart(options)`, `onRepeatWeekly(options)`
 * (saves the same answers as a Monday schedule, #562; absent hides it),
 * `githubConnected` (false offers the Toolbox instead of GitHub), `initial`
 * for a scene.
 */
export default function FeedPlanDialog({
  open, onOpenChange, onStart, onRepeatWeekly, githubConnected = true, initial = DEFAULT_FEED,
}) {
  const { t, i18n } = useLingui();
  const [options, setOptions] = useState(() => ({
    ...initial,
    sources: githubConnected ? initial.sources : initial.sources.filter((s) => s !== FeedSource.GITHUB),
  }));
  const set = (key) => (value) => setOptions((o) => ({ ...o, [key]: value }));
  const toggleSource = (source, on) =>
    setOptions((o) => ({
      ...o,
      sources: on ? [...new Set([...o.sources, source])] : o.sources.filter((s) => s !== source),
    }));
  const nothingPicked = options.sources.length === 0;

  function handleSubmit(event) {
    event.preventDefault();
    if (!nothingPicked) onStart?.(options);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
          <DialogHeader>
            <DialogTitle><Trans>Plan from what you shipped</Trans></DialogTitle>
            <DialogDescription>
              <Trans>
                Duct reads your work, leaves out the noise and shows you the stories it found. You pick
                which to tell, and nothing changes in your plan until you accept it.
              </Trans>
            </DialogDescription>
          </DialogHeader>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium"><Trans>Read</Trans></legend>
            {[FeedSource.GITHUB, FeedSource.DUCT].map((source) => {
              const disabled = source === FeedSource.GITHUB && !githubConnected;
              const id = `feed-source-${source}`;
              return (
                <div key={source} className="flex items-start gap-2">
                  <Checkbox
                    id={id}
                    checked={options.sources.includes(source)}
                    disabled={disabled}
                    onCheckedChange={(on) => toggleSource(source, on === true)}
                  />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <Label htmlFor={id} className={cn(disabled && "text-muted-foreground")}>
                      {i18n._(SOURCE_LABELS[source])}
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {source === FeedSource.GITHUB ? (
                        disabled ? (
                          <Trans>Not connected. Connect a repository in the <a className="underline" href="/connections?connector=github">Toolbox</a>.</Trans>
                        ) : (
                          <Trans>Merged pull requests, releases and changelog edits.</Trans>
                        )
                      ) : (
                        <Trans>Briefs it wrote, changes you approved and what they did.</Trans>
                      )}
                    </p>
                  </div>
                </div>
              );
            })}
            {nothingPicked && (
              <p className="text-xs text-destructive" role="alert"><Trans>Pick at least one thing to read.</Trans></p>
            )}
          </fieldset>

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
            legend={t`Days it may change`}
            hint={t`Only days with no draft yet. The rest of your plan stays as it is.`}
            value={options.maxDays}
            onChange={set("maxDays")}
            options={MAX_DAYS_OPTIONS.map((n) => ({ key: n, label: String(n) }))}
          />
          <Choice
            legend={t`From a private repository, talk about`}
            hint={i18n._(DISCLOSURE_HINTS[options.disclosure])}
            value={options.disclosure}
            onChange={set("disclosure")}
            options={Object.values(Disclosure).map((d) => ({ key: d, label: i18n._(DISCLOSURE_LABELS[d]) }))}
          />

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange?.(false)}>
              <Trans>Cancel</Trans>
            </Button>
            {onRepeatWeekly && (
              <Button type="button" variant="outline" disabled={nothingPicked} onClick={() => onRepeatWeekly(options)}>
                <Trans>Repeat weekly</Trans>
              </Button>
            )}
            <Button type="submit" disabled={nothingPicked}>
              <Trans>Find stories</Trans>
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** One question, its answers as a row of radio buttons. */
function Choice({ legend, hint, value, onChange, options }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <p id={id} className="text-sm font-medium">{legend}</p>
      <div role="radiogroup" aria-labelledby={id} className="flex flex-wrap items-center gap-1 self-start rounded-lg border border-border/60 bg-muted/40 p-0.5">
        {options.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={value === key}
            onClick={() => onChange(key)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
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
