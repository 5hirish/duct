"use client";

import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import PlanKanban from "./PlanKanban";
import PipelineProgress from "../PipelineProgress";
import { ContentStep } from "../../lib/contentEvents";

// Loading ladder mirrors the audit report: the two fixed backend steps
// (LOAD_PROJECT, ENRICHING) plus a virtual synthesis stage the backend doesn't
// emit a step for (the long SDK turn that produces the plan). Labels are
// message descriptors (module-level), resolved with `i18n._` in the component.
const PLAN_STAGES = [
  { id: ContentStep.LOAD_PROJECT,    label: msg`Loading your brand & pillars` },
  { id: ContentStep.ENRICHING,       label: msg`Researching trends & history` },
  { id: ContentStep.SYNTHESIZE_PLAN, label: msg`Synthesizing your 30-day plan`, virtual: true },
];

const PLAN_LINES = [
  msg`Reviewing your content pillars…`,
  msg`Studying what's worked before…`,
  msg`Scanning trending sounds & hooks…`,
  msg`Mapping topics across 30 days…`,
  msg`Balancing pillars and formats…`,
  msg`Casting your narrator…`,
  msg`Sequencing the posting cadence…`,
];

/**
 * Right-pane viewport for plan_month sessions.
 * Re-renders on every PLAN_GENERATED event from the workspace.
 *
 * MVP: Kanban only. PlanCalendar lands in a follow-up phase.
 *
 * Props:
 *   - payload: { type: "plan", id, name, days[], character, ... }
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
        streamingSubtitle={t`Synthesizing your 30-day plan…`}
        idleSubtitle={t`Researching pillars and synthesizing the plan…`}
      />
    );
  }

  const narrator = payload.character?.name;
  const voice = payload.character?.voice;
  const dayCount = Array.isArray(payload.days) ? payload.days.length : 0;

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border/60 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{payload.name || <Trans>30-day plan</Trans>}</p>
          {narrator && (
            <p className="text-xs text-muted-foreground truncate">
              {voice ? <Trans>Narrator: {narrator} · {voice}</Trans> : <Trans>Narrator: {narrator}</Trans>}
            </p>
          )}
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          <Plural value={dayCount} one="# day" other="# days" />
        </span>
      </div>

      <PlanKanban plan={payload} onReviseDay={onReviseDay} />
    </div>
  );
}
