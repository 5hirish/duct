"use client";

import { StepStatus } from "../../lib/agentSteps";
import { Spinner } from "@/components/ui/spinner";

// A sub-agent dispatch is a step whose id is "<prefix>:<name>"; those render as
// parallel chips rather than rows.
const DISPATCH_PREFIX = "dispatch_subagent:";

/**
 * The plain step list above the transcript: one row per stage the agent has
 * entered, sub-agent dispatches as chips. `labels` maps step ids to text for
 * events that arrive without one. Audit keeps its own richer version with
 * per-step detail panels (audit/AuditStepProgress); everyone else uses this.
 */
export default function StepProgress({ steps, labels = {} }) {
  if (!steps || steps.length === 0) return null;

  const dispatchSteps = steps.filter((s) => s.step_id?.startsWith(DISPATCH_PREFIX));
  const pipelineSteps = steps.filter((s) => !s.step_id?.startsWith(DISPATCH_PREFIX));

  return (
    <div className="px-4 py-3 space-y-3 border-b border-border/60">
      {pipelineSteps.length > 0 && (
        <div className="space-y-1.5">
          {pipelineSteps.map((s, i) => (
            <StepRow key={`${s.step_id}-${i}`} step={s} labels={labels} />
          ))}
        </div>
      )}

      {dispatchSteps.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Sub-agents</p>
          <div className="flex flex-wrap gap-1.5">
            {dispatchSteps.map((s) => (
              <DispatchChip key={s.step_id} step={s} />
            ))}
          </div>
        </div>
      )}
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
  if (status === StepStatus.RUNNING) return <Spinner className="size-2 text-blue-500" />;
  if (status === StepStatus.SUCCESS) return <span className="inline-block size-2 shrink-0 rounded-full bg-green-500" />;
  if (status === StepStatus.ERROR) return <span className="inline-block size-2 shrink-0 rounded-full bg-destructive" />;
  return <span className="inline-block size-2 shrink-0 rounded-full bg-muted-foreground/40" />;
}

function DispatchChip({ step }) {
  const name = step.step_id?.split(":", 2)[1] || "agent";
  const running = step.status === StepStatus.RUNNING;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
        running
          ? "border-blue-500/40 bg-blue-500/10 text-blue-600 dark:text-blue-400"
          : "border-border bg-muted/50 text-muted-foreground"
      }`}
      title={step.summary || ""}
    >
      {running && <span className="inline-block size-1.5 rounded-full bg-blue-500 animate-pulse" />}
      {name}
    </span>
  );
}
