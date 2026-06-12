"use client";

import PlanKanban from "./PlanKanban";
import PipelineProgress from "../PipelineProgress";
import { ContentStep } from "../../lib/contentEvents";

// Loading ladder mirrors the audit report: the two fixed backend steps
// (LOAD_PROJECT, ENRICHING) plus a virtual synthesis stage the backend doesn't
// emit a step for (the long SDK turn that produces the plan).
const PLAN_STAGES = [
  { id: ContentStep.LOAD_PROJECT,    label: "Loading your brand & pillars" },
  { id: ContentStep.ENRICHING,       label: "Researching trends & history" },
  { id: ContentStep.SYNTHESIZE_PLAN, label: "Synthesizing your 30-day plan", virtual: true },
];

const PLAN_LINES = [
  "Reviewing your content pillars…",
  "Studying what's worked before…",
  "Scanning trending sounds & hooks…",
  "Mapping topics across 30 days…",
  "Balancing pillars and formats…",
  "Casting your narrator…",
  "Sequencing the posting cadence…",
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
  if (!payload || payload.type !== "plan") {
    return (
      <PipelineProgress
        stages={PLAN_STAGES}
        steps={steps}
        activeId={ContentStep.SYNTHESIZE_PLAN}
        synthesising={building}
        virtualWaitsForPrior
        lines={PLAN_LINES}
        estimate="~3 min"
        buildingLabel="Building your plan"
        streamingSubtitle="Synthesizing your 30-day plan…"
        idleSubtitle="Researching pillars and synthesizing the plan…"
      />
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border/60 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{payload.name || "30-day plan"}</p>
          {payload.character?.name && (
            <p className="text-xs text-muted-foreground truncate">
              Narrator: {payload.character.name}
              {payload.character.voice ? ` · ${payload.character.voice}` : ""}
            </p>
          )}
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {Array.isArray(payload.days) ? payload.days.length : 0} days
        </span>
      </div>

      <PlanKanban plan={payload} onReviseDay={onReviseDay} />
    </div>
  );
}
