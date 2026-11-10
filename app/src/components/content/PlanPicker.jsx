"use client";

import { ChevronDown } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import PlanProgress from "@/components/content/PlanProgress";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import {
  PlanState,
  orderPlans,
  planChannels,
  planEndOf,
  planItems,
  planProgress,
  planStartOf,
  planState,
} from "@/lib/contentSchedule";
import { formatDateRange } from "@/lib/format";
import { planDisplayName } from "@/lib/planStrategy";

const STATE_WORDS = {
  [PlanState.RUNNING]: { label: msg`Current`, variant: "success" },
  [PlanState.UPCOMING]: { label: msg`Upcoming`, variant: "info" },
  [PlanState.ENDED]: { label: msg`Ended`, variant: "secondary" },
};

function nameOf(plan, t) {
  const shortId = String(plan?.id || "").slice(0, 8);
  return planDisplayName(plan?.name) || t`Plan ${shortId}`;
}

/**
 * Which plan the board shows. The plan's name is the board's title and opens
 * a menu of every plan the project has, current first, then upcoming, then
 * ended (`orderPlans`), each saying its state, its dates, how far it got and
 * where it posts, so a plan is picked by what it is rather than by a name
 * that is often only its month.
 *
 * Props:
 *   - plans: the listing (days included), at least two
 *   - value: the plan shown
 *   - onChange(id)
 *   - today: a Date at the start of the day
 *   - defaultOpen: open on mount, for /preview
 */
export default function PlanPicker({ plans, value, onChange, today, defaultOpen = false }) {
  const { t } = useLingui();
  const active = plans.find((p) => p.id === value) || null;
  const name = active ? nameOf(active, t) : t`Select a plan`;
  return (
    <DropdownMenu defaultOpen={defaultOpen}>
      <DropdownMenuTrigger
        aria-label={t`Plan: ${name}`}
        className="-ml-2 inline-flex h-8 w-fit max-w-full items-center gap-1.5 self-start rounded-md px-2 text-sm font-semibold outline-none transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/40 data-[state=open]:bg-accent"
      >
        <span className="truncate">{name}</span>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        // Wide enough for a row's dates, bar and counts on one line; on a
        // phone the channels give way so the line keeps its room.
        className="@container w-[min(38rem,calc(100vw-2rem))] max-h-[min(26rem,var(--radix-dropdown-menu-content-available-height))] overflow-y-auto"
      >
        <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
          {orderPlans(plans, today).map((plan) => (
            <DropdownMenuRadioItem
              key={plan.id}
              value={plan.id}
              className="items-start py-2.5 data-[state=checked]:bg-accent/50"
            >
              <PlanSummary plan={plan} today={today} />
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** One plan as the picker lists it: name and state, dates and progress, channels. */
export function PlanSummary({ plan, today }) {
  const { t, i18n } = useLingui();
  const items = planItems(plan, {}, { locale: i18n.locale, today });
  const progress = planProgress(items);
  const state = planState(plan, today);
  const channels = planChannels(items);
  const word = STATE_WORDS[state];
  const name = nameOf(plan, t);
  const period = formatDateRange(planStartOf(plan), planEndOf(plan), { locale: i18n.locale });
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium" title={name}>
            {name}
          </span>
          {word && (
            <Badge variant={word.variant} className="shrink-0">
              {i18n._(word.label)}
            </Badge>
          )}
        </div>
        {progress.total > 0 ? (
          <PlanProgress period={period} progress={progress} ended={state === PlanState.ENDED} />
        ) : (
          <p className="text-xs text-muted-foreground tabular-nums">{period}</p>
        )}
      </div>
      {channels.length > 0 && (
        <ul className="hidden shrink-0 items-center gap-1.5 @md:flex" aria-label={t`Channels`}>
          {channels.map(({ channel }) => (
            <li key={channel} title={platformMeta(channel).label}>
              <PlatformGlyph platform={channel} className="size-4" />
              <span className="sr-only">{platformMeta(channel).label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
