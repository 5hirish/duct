"use client";

import { Clock, FlaskConical, Lightbulb, TrendingUp } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { POST_TYPE_LABELS } from "@/lib/contentEnums";
import { TYPE_ICON } from "@/components/content/PostMiniCard";
import { ClampText } from "@/components/ui/clamp-text";

const STRATEGY_FIELDS = ["exploit", "exploit_evidence", "explore", "explore_evidence", "lesson", "best_times"];

/** True when a plan recorded any strategy. Plans made before #224 carry `{}`. */
export function hasStrategy(strategy) {
  return STRATEGY_FIELDS.some((k) => typeof strategy?.[k] === "string" && strategy[k].trim());
}

/**
 * What a plan chose from the account's own posting history, shown above the
 * plan: the post type it doubles down on, the one it tests, the evidence for
 * each, and — when the plan recorded them — what past posts taught it and when
 * to post. The evidence is the agent's sentence, written in the language Duct
 * writes to this person, so it is shown as written rather than translated.
 *
 * Renders nothing for a plan with no strategy.
 *
 * Props:
 *   - strategy: ContentPlan.strategy — { exploit, exploit_evidence, explore,
 *     explore_evidence, lesson, best_times }
 */
export default function PlanStrategy({ strategy }) {
  const { t } = useLingui();
  if (!hasStrategy(strategy)) return null;
  const s = strategy;

  return (
    // @container, not viewport breakpoints: this sits both on the full-width
    // Plan tab and in SplitWorkspace's resizable right pane.
    <section aria-label={t`Plan strategy`} className="@container shrink-0 border-b border-border/60 px-4 py-3">
      <div className="grid gap-3 @xl:grid-cols-2">
        <Choice
          icon={TrendingUp}
          tone="text-success"
          label={<Trans>Doubling down on</Trans>}
          type={s.exploit}
          evidence={s.exploit_evidence}
          none={<Trans>Nothing proven yet</Trans>}
        />
        <Choice
          icon={FlaskConical}
          tone="text-info"
          label={<Trans>Testing</Trans>}
          type={s.explore}
          evidence={s.explore_evidence}
          none={<Trans>Every type has results</Trans>}
        />
      </div>
      {(s.lesson || s.best_times) && (
        <dl className="mt-3 grid gap-1.5 text-xs">
          {s.lesson && <Note icon={Lightbulb} term={<Trans>Learned</Trans>} text={s.lesson} />}
          {s.best_times && <Note icon={Clock} term={<Trans>Best times</Trans>} text={s.best_times} />}
        </dl>
      )}
    </section>
  );
}

function Choice({ icon: Icon, tone, label, type, evidence, none }) {
  const { i18n } = useLingui();
  const TypeIcon = TYPE_ICON[type];
  const typeLabel = POST_TYPE_LABELS[type];
  return (
    <div className="flex min-w-0 gap-2.5">
      <Icon className={`mt-0.5 size-4 shrink-0 ${tone}`} aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <p className="text-xs text-muted-foreground">{label}</p>
        {type ? (
          <p className="flex items-center gap-1.5 text-sm font-medium">
            {TypeIcon && <TypeIcon className="size-3.5 shrink-0" aria-hidden />}
            {typeLabel ? i18n._(typeLabel) : type}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">{none}</p>
        )}
        {evidence && <ClampText text={evidence} lines={2} className="text-xs text-muted-foreground" />}
      </div>
    </div>
  );
}

function Note({ icon: Icon, term, text }) {
  return (
    <div className="flex min-w-0 items-start gap-2.5">
      {/* A size-4 slot, so the notes' text lines up with the choices' above. */}
      <span className="flex w-4 shrink-0 justify-center pt-px">
        <Icon className="size-3.5 text-muted-foreground" aria-hidden />
      </span>
      <dt className="shrink-0 font-medium">{term}</dt>
      <dd className="min-w-0 text-muted-foreground">
        <ClampText text={text} lines={2} />
      </dd>
    </div>
  );
}
