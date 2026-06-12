"use client";

import { useEffect, useState } from "react";
import { StepStatus } from "../lib/agentSteps";

/**
 * Shared "Duct is working" progress panel for the right viewport of every
 * streaming agent (SEO audit, Content Studio, …). Renders the Duct wordmark, a
 * rotating subtitle, a step ladder (✓ done / spinner active / hollow pending),
 * and a slow-filling progress bar. Extracted from the audit report so agents
 * stop re-forking this UI — same philosophy as the shared split shell
 * ([[project_split_workspace_shell]]).
 *
 * Two orthogonal "working" sub-states drive the visuals:
 *   - synthesising — the long analysis phase (slow-fill bar, rotating lines,
 *     spinner on the `activeId` stage). Defaults to "is the activeId step
 *     RUNNING?"; pass a bool to force it (content has no backend synth step).
 *   - writing — the final output is streaming (85%-pulse bar, "writing…").
 *
 * Props:
 *   - stages: [{ id, label, virtual?, conditional? }]
 *       virtual     — not a backend step; status is derived from synthesising /
 *                     writing (for synthesis / write phases the backend doesn't
 *                     emit a step for).
 *       conditional — only render once a step with this id is emitted (e.g.
 *                     enrichment, skipped in some flows).
 *   - steps: live [{ step_id, status, payload }] from the workspace.
 *   - activeId: the focal synthesis stage (real step id, or a virtual id) — its
 *       RUNNING row shows the time estimate and gates the synthesising visuals.
 *   - writingId: a virtual stage that runs during `writing` (e.g. WRITE_REPORT).
 *   - synthesising / writing: see above.
 *   - lines: rotating subtitle strings shown while synthesising.
 *   - estimate: e.g. "~3 min".
 *   - buildingLabel / streamingLabel: progress-bar captions.
 *   - streamingSubtitle / idleSubtitle: subtitle fallbacks.
 *   - virtualWaitsForPrior: a virtual stage only flips to RUNNING once every
 *       preceding visible stage has finished — use for a synthesis stage that
 *       follows fixed setup steps so they don't both spin at once.
 *   - stageChip(stage, step, status): optional extra right-aligned content.
 */
export default function PipelineProgress({
  stages,
  steps = [],
  activeId = null,
  writingId = null,
  synthesising,
  writing = false,
  lines = [],
  estimate = "~3 min",
  buildingLabel = "Building report",
  streamingLabel = "Generating report",
  streamingSubtitle = "Writing your report…",
  idleSubtitle = "Working on your report…",
  virtualWaitsForPrior = false,
  stageChip,
}) {
  // Self-driven ticker so the subtitle keeps rotating even through the long,
  // quiet stretches of synthesis when no new events arrive to re-render us.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 3000);
    return () => clearInterval(id);
  }, []);

  // Conditional stages only appear once the backend has emitted them.
  const visibleStages = stages.filter(
    (st) => !(st.conditional && !steps.find((s) => s.step_id === st.id)),
  );

  const activeStep = activeId ? steps.find((s) => s.step_id === activeId) : null;
  // Default the synthesis state to "the focal step is running"; let callers
  // force it for agents whose synthesis isn't a backend step (content).
  const inSynthesis = (synthesising ?? activeStep?.status === StepStatus.RUNNING) || writing;

  const subtitle = writing
    ? streamingSubtitle
    : inSynthesis && lines.length
    ? lines[tick % lines.length]
    : idleSubtitle;

  function statusFor(stage, idx) {
    if (!stage.virtual) {
      return steps.find((s) => s.step_id === stage.id)?.status ?? "pending";
    }
    // Virtual stages are driven by the synthesising / writing sub-states.
    let active;
    if (writingId && stage.id === writingId) active = writing;
    else if (stage.id === activeId) active = synthesising ?? false;
    else active = false;
    if (!active) return "pending";
    if (virtualWaitsForPrior) {
      const priorDone = visibleStages.slice(0, idx).every((s) => {
        if (s.virtual) return true;
        const st = steps.find((x) => x.step_id === s.id);
        return st && (st.status === StepStatus.SUCCESS || st.status === StepStatus.ERROR);
      });
      if (!priorDone) return "pending";
    }
    return StepStatus.RUNNING;
  }

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 py-12 text-center select-none">
      {/* Brand + animation */}
      <div className="mb-8 space-y-3">
        <div className="flex items-center justify-center gap-2">
          <span className="text-2xl font-bold tracking-tight">Duct</span>
          <span className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="inline-block size-1.5 rounded-full bg-primary animate-bounce"
                style={{ animationDelay: `${i * 0.18}s` }}
              />
            ))}
          </span>
        </div>
        <p className="text-sm text-muted-foreground min-h-[1.25rem] transition-all">{subtitle}</p>
      </div>

      {/* Step list */}
      <div className="w-full max-w-xs space-y-2 text-left">
        {visibleStages.map((stage, idx) => {
          const status = statusFor(stage, idx);
          const step = stage.virtual ? null : steps.find((s) => s.step_id === stage.id);
          const running = status === StepStatus.RUNNING;
          const isActive = stage.id === activeId;

          return (
            <div
              key={stage.id}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all duration-300 ${
                running
                  ? "bg-primary/8 border border-primary/20"
                  : status === StepStatus.SUCCESS
                  ? "opacity-50"
                  : "opacity-20"
              }`}
            >
              {running ? (
                <span className="size-3.5 shrink-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              ) : status === StepStatus.SUCCESS ? (
                <span className="text-green-500 text-sm shrink-0">✓</span>
              ) : (
                <span className="size-3.5 shrink-0 rounded-full border border-muted-foreground/30" />
              )}
              <span className="text-sm flex-1">{stage.label}</span>
              {running && isActive && (
                <span className="text-xs text-muted-foreground shrink-0">{estimate}</span>
              )}
              {running && !isActive && stage.virtual && (
                <span className="text-xs text-muted-foreground shrink-0 animate-pulse">writing…</span>
              )}
              {running && !isActive && !stage.virtual && (
                <span className="text-xs text-muted-foreground shrink-0 animate-pulse">now</span>
              )}
              {stageChip ? stageChip(stage, step, status) : null}
            </div>
          );
        })}
      </div>

      {/* Progress bar — slow fill during analysis, pulse at ~85% during writing */}
      {inSynthesis && (
        <div className="mt-6 w-full max-w-xs">
          <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
            <span>{writing ? streamingLabel : buildingLabel}</span>
            {!writing && <span>{estimate}</span>}
          </div>
          <div className="h-1 w-full rounded-full bg-muted overflow-hidden">
            {writing ? (
              <div className="h-full w-[85%] rounded-full bg-primary animate-pulse" />
            ) : (
              <div
                className="h-full rounded-full bg-primary origin-left"
                style={{ animation: "duct-progress 180s cubic-bezier(0.1, 0, 0.25, 1) forwards" }}
              />
            )}
          </div>
          <style>{`
            @keyframes duct-progress {
              from { width: 0% }
              to   { width: 82% }
            }
          `}</style>
        </div>
      )}
    </div>
  );
}
