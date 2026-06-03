"use client";

import { STEP_LABELS, ContentStep } from "../../lib/contentEvents";

/**
 * Renders the pipeline step list above the chat — one row per step the
 * agent has entered. Sub-agent dispatches (step_id starts with
 * "dispatch_subagent:") render as parallel progress chips.
 *
 * Simpler than AuditStepProgress: no per-step expandable detail panels
 * (we don't have sitemap/crawl payloads to surface for content).
 */
export default function ContentStepProgress({ steps }) {
  if (!steps || steps.length === 0) return null;

  const dispatchSteps = steps.filter((s) => s.step_id?.startsWith(`${ContentStep.DISPATCH_SUBAGENT}:`));
  const pipelineSteps = steps.filter((s) => !s.step_id?.startsWith(`${ContentStep.DISPATCH_SUBAGENT}:`));

  return (
    <div className="px-4 py-3 space-y-3 border-b border-border/60">
      {pipelineSteps.length > 0 && (
        <div className="space-y-1.5">
          {pipelineSteps.map((s) => (
            <StepRow key={s.step_id} step={s} />
          ))}
        </div>
      )}

      {dispatchSteps.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
            Sub-agents
          </p>
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

function StepRow({ step }) {
  const label = step.label || STEP_LABELS[step.step_id] || step.step_id;
  return (
    <div className="flex items-center gap-2 text-xs">
      <StatusDot status={step.status} />
      <span className={step.status === "running" ? "text-foreground" : "text-muted-foreground"}>
        {label}
      </span>
    </div>
  );
}

function StatusDot({ status }) {
  if (status === "running") {
    return <span className="inline-block size-2 shrink-0 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />;
  }
  if (status === "success") {
    return <span className="inline-block size-2 shrink-0 rounded-full bg-green-500" />;
  }
  if (status === "error" || status === "failed") {
    return <span className="inline-block size-2 shrink-0 rounded-full bg-destructive" />;
  }
  return <span className="inline-block size-2 shrink-0 rounded-full bg-muted-foreground/40" />;
}

function DispatchChip({ step }) {
  const name = step.step_id?.split(":", 2)[1] || "agent";
  const running = step.status === "running";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
        running
          ? "border-blue-500/40 bg-blue-500/10 text-blue-600 dark:text-blue-400"
          : "border-border bg-muted/50 text-muted-foreground"
      }`}
      title={step.summary || ""}
    >
      {running && (
        <span className="inline-block size-1.5 rounded-full bg-blue-500 animate-pulse" />
      )}
      {name}
    </span>
  );
}
