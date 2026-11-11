"use client";

import { useState } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { ArrowRight, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { GitHubMark } from "@/components/connections/logos";
import { feedSummary, sieveStones } from "@/lib/contentFeed";
import { LEFT_OUT_LABELS } from "@/lib/contentFeedLabels";
import { formatDateRange } from "@/lib/format";
import { cn } from "@/lib/utils";
import SourceChips from "./SourceChips";

const KEPT = "kept";
const LEFT = "left";

/**
 * What a plan from shipped work read, drawn before any plan exists and kept
 * above it after. Provenance before plans: the person sees what the stories
 * will stand on before being asked which to tell.
 *
 * The picture is the sieve: one stone for every thing the read saw, the kept
 * ones in their kind's colour, the noise left grey. "23 left out" is a claim;
 * twenty-three grey stones beside five coloured ones is the claim shown.
 * Pointing at a reason lights its stones, as the Toolbox's channel map lights
 * one channel, by opacity and never by looping.
 *
 * When the read found nothing worth a post, the run ended there with no
 * model call, and this is the whole pane: the sieve, every stone grey, and
 * the two ways on, a longer look back or a plan from goals.
 *
 * Props:
 *   - payload: the read step's payload (backend FeedDigest.payload)
 *   - onLookFurther?() / onPlanFromGoals?(): the "nothing new" actions
 */
export default function FeedSummary({ payload, onLookFurther, onPlanFromGoals }) {
  const { i18n } = useLingui();
  const [lit, setLit] = useState(null);
  const [open, setOpen] = useState(false);
  const s = feedSummary(payload);
  const sieve = sieveStones(s);
  const span = s.from && s.to
    ? formatDateRange(new Date(`${s.from}T00:00:00`), new Date(`${s.to}T00:00:00`), { locale: i18n.locale })
    : "";
  const kept = s.items.length;
  const total = sieve.total;
  const left = s.leftOutTotal;

  const reasons = (
    <ul className="flex flex-wrap gap-1" onMouseLeave={() => setLit(null)}>
      {s.leftOut.map(({ reason, count }) => (
        <li key={reason}>
          <button
            type="button"
            onMouseEnter={() => setLit(reason)}
            onFocus={() => setLit(reason)}
            onBlur={() => setLit(null)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs text-muted-foreground transition-colors",
              "hover:bg-muted hover:text-foreground focus-visible:bg-muted",
              lit === reason && "bg-muted text-foreground",
            )}
          >
            <span className="feed-sieve-stone" data-left aria-hidden />
            {LEFT_OUT_LABELS[reason] ? i18n._(LEFT_OUT_LABELS[reason]) : reason}
            <span className="tabular-nums">{count}</span>
          </button>
        </li>
      ))}
    </ul>
  );

  if (!s.worth) {
    const nothingAtAll = total === 0;
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Card className="flex w-full max-w-md flex-col gap-4">
          {nothingAtAll ? (
            <span className="flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground" aria-hidden>
              <span className="size-5"><GitHubMark /></span>
            </span>
          ) : (
            <Sieve sieve={sieve} lit={lit} size="lg" />
          )}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold">
              {nothingAtAll ? <Trans>Nothing came back</Trans> : <Trans>Nothing new worth a post yet</Trans>}
            </p>
            <p className="text-sm text-muted-foreground">
              {nothingAtAll ? (
                <Trans>Duct had no work to read. Is a repository connected for this project?</Trans>
              ) : span ? (
                <Trans>Duct read {total} things from {span}. None would make a reader stop, so it spent nothing and changed nothing.</Trans>
              ) : (
                <Trans>Duct read {total} things. None would make a reader stop, so it spent nothing and changed nothing.</Trans>
              )}
            </p>
          </div>
          {kept > 0 && <SourceChips sources={s.items} max={4} />}
          {left > 0 && reasons}
          <div className="flex flex-wrap gap-2">
            {nothingAtAll ? (
              <Button asChild size="sm">
                <a href="/connections?connector=github"><Trans>Connect GitHub</Trans></a>
              </Button>
            ) : onLookFurther && (
              <Button size="sm" onClick={onLookFurther}><Trans>Look back 30 days</Trans></Button>
            )}
            {onPlanFromGoals && (
              <Button size="sm" variant="ghost" onClick={onPlanFromGoals}>
                <Trans>Plan from your goals</Trans> <ArrowRight className="size-3.5" aria-hidden />
              </Button>
            )}
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2.5 border-b border-border/60 px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground"><Trans>From your work</Trans></span>
          {span && <> · {span}</>}
        </p>
        <span className="text-xs text-muted-foreground">
          <Trans><span className="font-medium text-foreground tabular-nums">{kept}</span> of {total} kept</Trans>
        </span>
      </div>
      <Sieve sieve={sieve} lit={lit} />
      <SourceChips sources={s.items} max={5} />
      {left > 0 && (
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            onMouseEnter={() => !open && setLit(LEFT)}
            onMouseLeave={() => !open && setLit(null)}
            aria-expanded={open}
            className="inline-flex items-center gap-1 self-start text-xs text-muted-foreground hover:text-foreground"
          >
            <Plural value={left} one="# left out as noise" other="# left out as noise" />
            <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
          </button>
          {open && reasons}
        </div>
      )}
    </div>
  );
}

/**
 * The stones. `lit` is a reason (its stones light), LEFT (every left-out
 * stone) or KEPT; null draws them all as they are. One image to a reader,
 * with the count said in words.
 */
function Sieve({ sieve, lit, size = "sm" }) {
  const { t } = useLingui();
  const kept = sieve.stones.filter((st) => st.kept).length;
  const total = sieve.total;
  return (
    <div
      role="img"
      aria-label={t`${kept} of ${total} kept`}
      data-sieve-lit={lit && lit !== KEPT ? "" : undefined}
      data-size={size}
      className={cn("feed-sieve", size === "lg" && "max-w-sm")}
    >
      {sieve.stones.map((st) => (
        <span
          key={st.key}
          className={cn("feed-sieve-stone", st.kept && "feed-kind")}
          data-kind={st.kept ? st.kind : undefined}
          data-left={st.kept ? undefined : ""}
          data-lit={!st.kept && (lit === LEFT || lit === st.reason) ? "" : undefined}
        />
      ))}
      {sieve.hidden > 0 && <span className="self-center pl-1 text-2xs text-muted-foreground tabular-nums">+{sieve.hidden}</span>}
    </div>
  );
}
