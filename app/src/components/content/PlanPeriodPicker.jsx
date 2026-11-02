"use client";

// How far ahead a new plan looks: the month in progress, or the next 7, 14
// or 30 days. Each choice names the exact dates it will plan, worked out by
// the rules the run applies (lib/contentSchedule.js mirrors
// agents/content/plan_period.py), so nobody finds out the period after the
// agent has spent three minutes on it.
//
// Two shapes of one choice: a menu on a toolbar button, where room is short,
// and a row of toggles on the first-run screen, where the choice is the
// point and should be seen before the button is pressed.

import { useId } from "react";
import { ChevronDown } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PlanLength } from "@/lib/contentSchedule";
import { formatDateRange } from "@/lib/format";
import { cn } from "@/lib/utils";

const LENGTH_LABEL = Object.freeze({
  [PlanLength.WEEK]: msg`1 week`,
  [PlanLength.TWO_WEEKS]: msg`2 weeks`,
  [PlanLength.THIRTY_DAYS]: msg`30 days`,
});

/** "Rest of October", "November", "2 weeks"; or the day count, when a later
 * plan cut the period short and its usual name would overstate it. */
export function PeriodName({ option }) {
  const { i18n } = useLingui();
  const { length, start, days, clipped } = option;
  if (clipped) return <Plural value={days} one="# day" other="# days" />;
  if (length !== PlanLength.MONTH) return i18n._(LENGTH_LABEL[length]);
  const month = start.toLocaleDateString(i18n.locale, { month: "long" });
  if (start.getDate() !== 1) return <Trans>Rest of {month}</Trans>;
  // Standing alone it starts the label, and some locales write months lower-case.
  return month.charAt(0).toLocaleUpperCase(i18n.locale) + month.slice(1);
}

/**
 * A toolbar button that opens the choice. Props:
 *   - options: planPeriodOptions(...) — renders nothing when empty
 *   - onPick(option): start the plan
 *   - icon, variant, children: the button
 */
export function PlanPeriodMenu({ options, onPick, icon: Icon, variant = "default", children }) {
  const { i18n } = useLingui();
  if (!options?.length) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant={variant} className="h-8">
          {Icon && <Icon className="size-3.5" aria-hidden />} {children}
          <ChevronDown className="size-3.5 opacity-60" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-60">
        <DropdownMenuLabel><Trans>How far ahead?</Trans></DropdownMenuLabel>
        {options.map((o) => (
          <DropdownMenuItem key={o.length} onSelect={() => onPick(o)}>
            <span className="font-medium"><PeriodName option={o} /></span>
            <span className="ml-auto pl-4 text-xs tabular-nums text-muted-foreground">
              {formatDateRange(o.start, o.end, { locale: i18n.locale })}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * The same choice laid out as toggles, for a screen where it leads up to
 * the button. Props: options, value (a PlanLength), onChange(length).
 */
export function PlanPeriodToggle({ options, value, onChange }) {
  const labelId = useId();
  if (!options?.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span id={labelId} className="text-xs font-medium text-muted-foreground">
        <Trans>How far ahead?</Trans>
      </span>
      <div
        role="group"
        aria-labelledby={labelId}
        className="flex flex-wrap items-center gap-1 rounded-lg border border-border/60 bg-muted/40 p-0.5"
      >
        {options.map((o) => (
          <button
            key={o.length}
            type="button"
            aria-pressed={value === o.length}
            onClick={() => onChange(o.length)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              value === o.length
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <PeriodName option={o} />
          </button>
        ))}
      </div>
    </div>
  );
}
