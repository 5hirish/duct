"use client";

import { useState } from "react";
import { STEP_LABELS, ContentStep } from "../../lib/contentEvents";
import { StepStatus } from "../../lib/agentSteps";

/**
 * Renders the pipeline step list above the chat — one row per step the agent
 * has entered. Sub-agent dispatches (step_id starts with "dispatch_subagent:")
 * are grouped under a "Sub-agents" heading.
 *
 * Any step that carries a `summary` (sub-agent briefs/results, web-search
 * queries) is expandable — click the row to reveal what the agent researched,
 * mirroring the audit agent's expandable step detail.
 */
export default function ContentStepProgress({ steps }) {
  const [expanded, setExpanded] = useState(() => new Set());

  if (!steps || steps.length === 0) return null;

  function toggle(id) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const dispatchSteps = steps.filter((s) => s.step_id?.startsWith(`${ContentStep.DISPATCH_SUBAGENT}:`));
  const pipelineSteps = steps.filter((s) => !s.step_id?.startsWith(`${ContentStep.DISPATCH_SUBAGENT}:`));

  return (
    <div className="space-y-3 border-b border-border/60 px-4 py-3">
      {pipelineSteps.length > 0 && (
        <div className="space-y-1.5">
          {pipelineSteps.map((s) => (
            <StepRow key={s.step_id} step={s} expanded={expanded.has(s.step_id)} onToggle={() => toggle(s.step_id)} />
          ))}
        </div>
      )}

      {dispatchSteps.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Sub-agents</p>
          {dispatchSteps.map((s) => (
            <StepRow key={s.step_id} step={s} subagent expanded={expanded.has(s.step_id)} onToggle={() => toggle(s.step_id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function humanize(name) {
  return String(name || "agent").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function StepRow({ step, subagent, expanded, onToggle }) {
  const label = subagent
    ? step.label || humanize(step.step_id?.split(":", 2)[1])
    : step.label || STEP_LABELS[step.step_id] || step.step_id;
  const summary = (step.summary || "").trim();
  const canExpand = Boolean(summary);

  return (
    <div>
      <div
        className={`flex items-center gap-2 text-xs ${canExpand ? "cursor-pointer select-none" : ""}`}
        onClick={canExpand ? onToggle : undefined}
        role={canExpand ? "button" : undefined}
        tabIndex={canExpand ? 0 : undefined}
        aria-expanded={canExpand ? expanded : undefined}
        onKeyDown={canExpand ? (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); }
        } : undefined}
      >
        <StatusDot status={step.status} />
        <span className={`flex-1 truncate ${step.status === StepStatus.RUNNING ? "text-foreground" : "text-muted-foreground"}`}>
          {label}
        </span>
        {canExpand && (
          <span className={`shrink-0 text-[10px] text-muted-foreground/50 transition-transform ${expanded ? "rotate-90" : ""}`}>
            ›
          </span>
        )}
      </div>

      {canExpand && (
        <div className="ml-4 overflow-hidden transition-all duration-200" style={{ maxHeight: expanded ? "20rem" : "0px" }}>
          <p className="mt-1 max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted/50 p-2 text-[11px] leading-relaxed text-muted-foreground">
            {summary}
          </p>
        </div>
      )}
    </div>
  );
}

function StatusDot({ status }) {
  if (status === StepStatus.RUNNING) {
    return <span className="inline-block size-2 shrink-0 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />;
  }
  if (status === StepStatus.SUCCESS) {
    return <span className="inline-block size-2 shrink-0 rounded-full bg-green-500" />;
  }
  if (status === StepStatus.ERROR) {
    return <span className="inline-block size-2 shrink-0 rounded-full bg-destructive" />;
  }
  return <span className="inline-block size-2 shrink-0 rounded-full bg-muted-foreground/40" />;
}
