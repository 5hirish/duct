"use client";

import { CalendarDays } from "lucide-react";
import { Plural, useLingui } from "@lingui/react/macro";

/**
 * The one line under the plan's name: when it runs, and how far it has got,
 * as a bar with its words. The bar is the comparison every count needs;
 * posted, missed and still-to-come each have a word as well as a colour, so
 * the line reads in greyscale and to a screen reader. "0 of 23 posted" on
 * day one read as a failure; "23 to go" is the same fact the right way up.
 */
export default function PlanProgress({ period, progress, ended }) {
  const { t } = useLingui();
  const { total, posted, missed, drafted } = progress;
  const left = Math.max(total - posted - missed, 0);
  const pct = (n) => `${(n / total) * 100}%`;
  const label = ended
    ? t`${posted} of ${total} posted`
    : posted === 0 && missed === 0
      ? t`${left} to go`
      : t`${posted} posted · ${left} to go`;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {period && (
        <span className="inline-flex shrink-0 items-center gap-1.5">
          <CalendarDays className="size-3.5" aria-hidden="true" />
          <span className="tabular-nums">{period}</span>
        </span>
      )}
      <span
        className="flex h-1.5 w-28 shrink-0 overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={t`${posted} of ${total} posted, ${missed} missed, ${drafted} drafted`}
      >
        {posted > 0 && <span className="h-full bg-success" style={{ width: pct(posted) }} />}
        {missed > 0 && <span className="h-full bg-warning" style={{ width: pct(missed) }} />}
        {drafted > 0 && <span className="h-full bg-foreground/35" style={{ width: pct(drafted) }} />}
      </span>
      <span className="tabular-nums whitespace-nowrap">{label}</span>
      {missed > 0 && (
        <span className="tabular-nums whitespace-nowrap text-warning">
          <Plural value={missed} one="# missed" other="# missed" />
        </span>
      )}
    </div>
  );
}
