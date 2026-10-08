"use client";

import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import PlanList from "./PlanList";
import PlanStrategy from "./PlanStrategy";
import PipelineProgress from "../PipelineProgress";
import { ContentStep } from "../../lib/contentEvents";
import { planEndOf, planStartOf } from "../../lib/contentSchedule";
import { formatDateRange } from "../../lib/format";

// Loading ladder mirrors the audit report: the two fixed backend steps
// (LOAD_PROJECT, ENRICHING) plus a virtual synthesis stage the backend doesn't
// emit a step for (the long SDK turn that produces the plan). Labels are
// message descriptors (module-level), resolved with `i18n._` in the component.
const PLAN_STAGES = [
  { id: ContentStep.LOAD_PROJECT,    label: msg`Loading your brand & pillars` },
  { id: ContentStep.ENRICHING,       label: msg`Researching trends & history` },
  { id: ContentStep.SYNTHESIZE_PLAN, label: msg`Synthesizing your plan`, virtual: true },
];

const PLAN_LINES = [
  msg`Reviewing your content pillars…`,
  msg`Studying what's worked before…`,
  msg`Scanning trending sounds & hooks…`,
  msg`Mapping topics across your dates…`,
  msg`Balancing pillars and formats…`,
  msg`Casting your narrator…`,
  msg`Sequencing the posting cadence…`,
];

/**
 * Right-pane viewport for plan_month sessions.
 * Re-renders on every PLAN_GENERATED event from the workspace.
 *
 * The plan reads as a list, not a status board: while a plan is being
 * written every post is pending, and a Kanban of that is one full lane and
 * three empty ones. The Plan tab keeps the board for when posts move.
 *
 * Props:
 *   - payload: { type: "plan", id, name, days[], character, strategy, ... }
 *   - steps: live pipeline steps from the workspace (drives the loading ladder)
 *   - building: the plan is still being built (no payload yet, run not failed)
 *   - onReviseDay?(dayIndex)
 */
export default function PlanViewport({ payload, steps = [], building = false, onReviseDay }) {
  const { t, i18n } = useLingui();
  if (!payload || payload.type !== "plan") {
    return (
      <PipelineProgress
        stages={PLAN_STAGES.map((s) => ({ ...s, label: i18n._(s.label) }))}
        steps={steps}
        activeId={ContentStep.SYNTHESIZE_PLAN}
        synthesising={building}
        virtualWaitsForPrior
        lines={PLAN_LINES.map((m) => i18n._(m))}
        estimate={t`~3 min`}
        buildingLabel={t`Building your plan`}
        streamingSubtitle={t`Synthesizing your plan…`}
        idleSubtitle={t`Researching pillars and synthesizing the plan…`}
      />
    );
  }

  const narrator = payload.character?.name;
  const voice = payload.character?.voice;
  const dayCount = Array.isArray(payload.days) ? payload.days.length : 0;
  // The period this plan manages, so a revision reads as "this plan", not "a plan".
  const period = formatDateRange(planStartOf(payload), planEndOf(payload), { locale: i18n.locale });

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border/60 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{payload.name || <Trans>Content plan</Trans>}</p>
          {narrator && (
            <p className="text-xs text-muted-foreground truncate">
              {voice ? <Trans>Narrator: {narrator} · {voice}</Trans> : <Trans>Narrator: {narrator}</Trans>}
            </p>
          )}
        </div>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {period && <>{period} · </>}
          <Plural value={dayCount} one="# day" other="# days" />
        </span>
      </div>

      <PlanStrategy strategy={payload.strategy} />
      <PlanList plan={payload} onReviseDay={onReviseDay} />
    </div>
  );
}
