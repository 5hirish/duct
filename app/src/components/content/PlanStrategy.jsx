"use client";

import { Clock, Compass, FlaskConical, TrendingUp } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { POST_TYPE_LABELS } from "@/lib/contentEnums";
import { TYPE_ICON } from "@/components/content/PostMiniCard";
import { HelpTip } from "@/components/ui/page";
import { titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

const STRATEGY_FIELDS = ["exploit", "exploit_evidence", "explore", "explore_evidence", "lesson", "best_times"];

/** True when a plan recorded any strategy. Plans made before #224 carry `{}`. */
export function hasStrategy(strategy) {
  return STRATEGY_FIELDS.some((k) => typeof strategy?.[k] === "string" && strategy[k].trim());
}

/** How many of the plan's posts are each type, most first: the mix as the plan has it. */
export function typeMix(days) {
  const counts = new Map();
  for (const d of Array.isArray(days) ? days : []) {
    const type = d?.post_type || "";
    if (type) counts.set(type, (counts.get(type) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([type, count]) => ({ type, count }));
}

/**
 * What the plan chose, in one line built from data, with the agent's reasons
 * one click away.
 *
 * It used to be four rows of the agent's sentences, and with no posting
 * history they said little that was true: "Doubling down on: Nothing proven
 * yet" under a rising arrow, a "Testing: Slideshow" whose own evidence named
 * three types, an "exploit leader" from the prompt's vocabulary, and a
 * "Learned" that was a goal. So the line is code's: what the plan scales and
 * tests when it has evidence, and otherwise the mix it is trying, counted from
 * its own days. The agent's evidence, lesson and times are behind the "?",
 * where a reader who wants the why can have it.
 *
 * Props:
 *   - strategy: ContentPlan.strategy — { exploit, exploit_evidence, explore,
 *     explore_evidence, lesson, best_times }
 *   - days: the plan's days, for the mix
 *   - className: the board sets its own spacing; the default is a pane's strip
 */
export default function PlanStrategy({ strategy, days = [], className }) {
  const { t } = useLingui();
  const s = strategy || {};
  const mix = typeMix(days);
  if (!hasStrategy(s) && mix.length < 2) return null;

  // A proven type is the one fact that needs history; without it, the
  // lesson field is whatever the model put there, never a lesson.
  const proven = Boolean(s.exploit);
  const why = [
    proven && s.exploit_evidence && { term: <Trans>Why scale it</Trans>, text: s.exploit_evidence },
    s.explore && s.explore_evidence && { term: <Trans>Why test it</Trans>, text: s.explore_evidence },
    proven && s.lesson && { term: <Trans>Learned</Trans>, text: s.lesson },
    s.best_times && { term: <Trans>Best times</Trans>, text: s.best_times },
  ].filter(Boolean);

  return (
    <section
      aria-label={t`Plan strategy`}
      className={cn("@container flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 text-xs", className ?? "border-b border-border/60 px-4 py-3")}
    >
      {proven ? (
        <>
          <Fact icon={TrendingUp} tone="text-success" label={<Trans>Scaling</Trans>}>
            <TypeChip type={s.exploit} />
          </Fact>
          {s.explore && (
            <Fact icon={FlaskConical} tone="text-info" label={<Trans>Testing</Trans>}>
              <TypeChip type={s.explore} />
            </Fact>
          )}
        </>
      ) : (
        mix.length > 0 && (
          <Fact icon={Compass} tone="text-info" label={<Trans>Finding what works</Trans>}>
            {mix.map(({ type, count }) => (
              <TypeChip key={type} type={type} count={count} />
            ))}
          </Fact>
        )
      )}
      {s.best_times && (
        <Fact icon={Clock} tone="text-muted-foreground" label={<Trans>Best times</Trans>}>
          {/* The agent's words; one line here, the whole of it under "?". */}
          <span className="max-w-64 truncate text-foreground">{s.best_times}</span>
        </Fact>
      )}
      {why.length > 0 && (
        <HelpTip label={t`Why this plan`} className="-my-1.5">
          <dl className="grid gap-3 text-sm">
            {why.map((row, i) => (
              <div key={i}>
                <dt className="font-medium">{row.term}</dt>
                <dd className="text-muted-foreground">{row.text}</dd>
              </div>
            ))}
          </dl>
        </HelpTip>
      )}
    </section>
  );
}

function Fact({ icon: Icon, tone, label, children }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <Icon className={cn("size-3.5 shrink-0", tone)} aria-hidden />
      <span className="text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function TypeChip({ type, count }) {
  const { i18n } = useLingui();
  const Icon = TYPE_ICON[type];
  const label = POST_TYPE_LABELS[type] ? i18n._(POST_TYPE_LABELS[type]) : titleCase(type);
  return (
    <span className="inline-flex items-center gap-1 font-medium text-foreground">
      {Icon && <Icon className="size-3.5 shrink-0" aria-hidden />}
      {label}
      {count != null && <span className="font-normal tabular-nums text-muted-foreground">{count}</span>}
    </span>
  );
}
