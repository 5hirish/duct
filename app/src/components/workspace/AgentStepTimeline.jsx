"use client";

import { useState } from "react";
import { StepStatus } from "../../lib/agentSteps";

/**
 * AgentStepTimeline — the ONE shared step/progress primitive every agent renders
 * through (audit, content/clone, and any future agent). It exists to stop the
 * regression where each new agent re-forked a weaker step list: the rich
 * behaviour (status icons, expand/collapse, per-step detail panels, inline
 * meta) lives here once, and agents supply only their own labels + detail
 * renderers.
 *
 * Step shape (the standard SSE step contract — mirrors backend
 * agents/core/events.py STEP_* events):
 *   { step_id, label, status: "running"|"success"|"error", summary?, payload? }
 *
 * Props:
 *   steps             — the step array (above).
 *   labels            — optional { [step_id]: "Human label" } map.
 *   detailComponents  — optional { [step_id]: ({payload, step}) => node } map.
 *                       Rendered (expandable) when the step is done AND has a payload.
 *   renderMeta        — optional (step) => node shown inline on the right of the
 *                       row (counts, badges). Audit uses this for page/competitor counts.
 *   renderBelow       — optional (step) => node shown under the row header, outside
 *                       the expand panel (audit uses it for the synthesize progress bar).
 *   size              — "sm" (default, audit) | "xs" (content), row text size.
 *   className         — wrapper class (spacing).
 *
 * Expand precedence: a step with a detailComponent + payload shows the rich
 * panel; otherwise a step with a `summary` string shows a plain-text panel
 * (the simple-agent fallback). A step with neither is a non-expandable row.
 */
export default function AgentStepTimeline({
  steps,
  labels,
  detailComponents,
  renderMeta,
  renderBelow,
  size = "sm",
  className = "space-y-2.5 py-2",
}) {
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

  return (
    <div className={className}>
      {steps.map((step) => (
        <StepRow
          key={step.step_id}
          step={step}
          labels={labels}
          detailComponents={detailComponents}
          renderMeta={renderMeta}
          renderBelow={renderBelow}
          size={size}
          expanded={expanded.has(step.step_id)}
          onToggle={() => toggle(step.step_id)}
        />
      ))}
    </div>
  );
}

function StepRow({ step, labels, detailComponents, renderMeta, renderBelow, size, expanded, onToggle }) {
  const { step_id, label, status, payload } = step;
  const isRunning = status === StepStatus.RUNNING;
  const isDone = status === StepStatus.SUCCESS || status === StepStatus.ERROR;

  const Details = detailComponents?.[step_id];
  const summary = (step.summary || "").trim();
  const canExpandDetail = isDone && !!Details && payload != null;
  const canExpandSummary = !canExpandDetail && !!summary;
  const canExpand = canExpandDetail || canExpandSummary;

  const displayLabel = labels?.[step_id] || label || step_id;
  const meta = renderMeta ? renderMeta(step) : null;
  const below = renderBelow ? renderBelow(step) : null;
  const textSize = size === "xs" ? "text-xs" : "text-sm";

  return (
    <div>
      {/* Header row */}
      <div
        className={`flex items-center gap-2 ${textSize} ${canExpand ? "cursor-pointer hover:opacity-80 transition-opacity select-none" : ""}`}
        onClick={canExpand ? onToggle : undefined}
        role={canExpand ? "button" : undefined}
        tabIndex={canExpand ? 0 : undefined}
        aria-expanded={canExpand ? expanded : undefined}
        onKeyDown={canExpand ? (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); }
        } : undefined}
      >
        <StatusIcon status={status} />
        <span className={`flex-1 min-w-0 truncate ${isRunning ? "font-medium text-foreground" : "text-muted-foreground"}`}>
          {displayLabel}
        </span>
        {meta}
        {canExpand && (
          <span className={`shrink-0 text-xs text-muted-foreground/50 transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}>
            ›
          </span>
        )}
      </div>

      {below}

      {/* Expandable detail panel */}
      {canExpand && (
        <div
          className="ml-5 overflow-hidden transition-all duration-200"
          style={{ maxHeight: expanded ? "700px" : "0px" }}
        >
          <div className="pt-2 pb-1">
            {canExpandDetail ? (
              <Details payload={payload} step={step} />
            ) : (
              <p className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted/50 p-2 text-[11px] leading-relaxed text-muted-foreground">
                {summary}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// One consistent status vocabulary for every agent: spinning ring (running),
// ✓ (success), ✗ (error), hollow dot (pending/unknown).
function StatusIcon({ status }) {
  if (status === StepStatus.RUNNING) {
    return <span className="inline-block size-3 shrink-0 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />;
  }
  if (status === StepStatus.SUCCESS) {
    return <span className="shrink-0 text-xs text-green-500">✓</span>;
  }
  if (status === StepStatus.ERROR) {
    return <span className="shrink-0 text-xs text-destructive">✗</span>;
  }
  return <span className="size-3 shrink-0 rounded-full border border-muted-foreground/20" />;
}
