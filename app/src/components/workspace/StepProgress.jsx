"use client";

import { StepStatus } from "../../lib/agentSteps";
import { Spinner } from "@/components/ui/spinner";

// A sub-agent dispatch is a step whose id is "<prefix>:<name>"; the ladder
// filters those out, because the transcript draws them.
const DISPATCH_PREFIX = "dispatch_subagent:";

/**
 * The plain step list above the transcript: one row per stage the agent has
 * entered. `labels` maps step ids to text for events that arrive without one.
 * Audit keeps its own richer version with per-step detail panels
 * (audit/AuditStepProgress); everyone else uses this.
 *
 * Sub-agent dispatches used to render here as parallel chips. They are an
 * activity row in the transcript now (workspace/ActivityRow), where the brief
 * it was given and the answer it came back with fit — a chip could only ever
 * carry its name and a tooltip, and showing it in both places said the same
 * thing twice.
 */
export default function StepProgress({ steps, labels = {} }) {
  const rows = (steps || []).filter((s) => !s.step_id?.startsWith(DISPATCH_PREFIX));
  if (!rows.length) return null;
  return (
    <div className="space-y-1.5 border-b border-border/60 px-4 py-3">
      {rows.map((s, i) => (
        <StepRow key={`${s.step_id}-${i}`} step={s} labels={labels} />
      ))}
    </div>
  );
}

function StepRow({ step, labels }) {
  const label = step.label || labels[step.step_id] || step.step_id;
  return (
    <div className="flex items-center gap-2 text-xs">
      <StatusDot status={step.status} />
      <span className={step.status === StepStatus.RUNNING ? "text-foreground" : "text-muted-foreground"}>
        {label}
      </span>
    </div>
  );
}

function StatusDot({ status }) {
  if (status === StepStatus.RUNNING) return <Spinner className="size-2 text-info" />;
  if (status === StepStatus.SUCCESS) return <span className="inline-block size-2 shrink-0 rounded-full bg-success" />;
  if (status === StepStatus.ERROR) return <span className="inline-block size-2 shrink-0 rounded-full bg-destructive" />;
  return <span className="inline-block size-2 shrink-0 rounded-full bg-muted-foreground/40" />;
}
