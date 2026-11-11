"use client";

import { useState } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { ChevronDown, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { feedSummary } from "@/lib/contentFeed";
import { LEFT_OUT_LABELS } from "@/lib/contentFeedLabels";
import { formatDateRange } from "@/lib/format";
import { cn } from "@/lib/utils";
import SourceChips from "./SourceChips";

/**
 * What a plan from shipped work read, drawn before any plan exists and kept
 * above it after: the window, what made it through as chips, and one folded
 * line for what Duct left out and why. Provenance before plans: the person
 * sees what the stories will stand on before being asked which to tell.
 *
 * When the read found nothing worth a post, the run ended there with no
 * model call, and this is the whole pane: it says so, and offers the two
 * ways on, a longer look back or a plan from goals.
 *
 * Props:
 *   - payload: the read step's payload (backend FeedDigest.payload)
 *   - variant: "card" (the pane before a plan) | "strip" (above a plan)
 *   - onLookFurther?() / onPlanFromGoals?(): the "nothing new" actions
 */
export default function FeedSummary({ payload, variant = "card", onLookFurther, onPlanFromGoals }) {
  const { i18n } = useLingui();
  const [open, setOpen] = useState(false);
  const s = feedSummary(payload);
  const span = s.from && s.to
    ? formatDateRange(new Date(`${s.from}T00:00:00`), new Date(`${s.to}T00:00:00`), { locale: i18n.locale })
    : "";
  const count = s.items.length;
  const left = s.leftOutTotal;

  const leftOut = left > 0 && (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 self-start text-xs text-muted-foreground hover:text-foreground"
      >
        <Plural value={left} one="# item left out" other="# items left out" />
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <ul className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {s.leftOut.map(({ reason, count: n }) => (
            <li key={reason}>
              {LEFT_OUT_LABELS[reason] ? i18n._(LEFT_OUT_LABELS[reason]) : reason}: <span className="tabular-nums">{n}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  if (!s.worth) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Card className="flex max-w-md flex-col gap-3">
          <span className="flex size-9 items-center justify-center rounded-xl bg-muted text-muted-foreground" aria-hidden>
            <GitBranch className="size-4.5" />
          </span>
          <p className="text-sm font-semibold"><Trans>Nothing new worth a post yet</Trans></p>
          <p className="text-sm text-muted-foreground">
            {span ? (
              <Trans>Duct read {span} and found nothing a reader would notice, so it made no model call and changed nothing.</Trans>
            ) : (
              <Trans>Duct found nothing a reader would notice, so it made no model call and changed nothing.</Trans>
            )}
          </p>
          {count > 0 && <SourceChips sources={s.items} max={4} />}
          {leftOut}
          {count === 0 && left === 0 && (
            <p className="text-xs text-muted-foreground">
              <Trans>Nothing came back at all. If no repository is connected yet, <a className="underline" href="/connections?connector=github">connect one in the Toolbox</a>.</Trans>
            </p>
          )}
          {(onLookFurther || onPlanFromGoals) && (
            <div className="flex flex-wrap gap-2 pt-1">
              {onLookFurther && (
                <Button size="sm" variant="outline" onClick={onLookFurther}><Trans>Look back 30 days</Trans></Button>
              )}
              {onPlanFromGoals && (
                <Button size="sm" variant="ghost" onClick={onPlanFromGoals}><Trans>Plan from your goals</Trans></Button>
              )}
            </div>
          )}
        </Card>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-1.5", variant === "strip" ? "border-b border-border/60 px-4 py-2.5" : "p-4")}>
      <p className="text-xs font-medium text-muted-foreground">
        {span ? <Trans>From your work · {span}</Trans> : <Trans>From your work</Trans>}
        {" · "}
        <Plural value={count} one="# source" other="# sources" />
      </p>
      <SourceChips sources={s.items} max={variant === "strip" ? 4 : 8} />
      {leftOut}
    </div>
  );
}
