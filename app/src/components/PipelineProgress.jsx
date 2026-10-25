"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { StepStatus } from "../lib/agentSteps";
import { formatElapsed } from "../lib/format";
import { useElapsed } from "../hooks/useElapsed";
import { Spinner } from "@/components/ui/spinner";
import { Trans, useLingui } from "@lingui/react/macro";

/**
 * Shared "Duct is working" progress panel for the right viewport of every
 * streaming agent (SEO audit, Content Studio, …). Renders the Duct wordmark, a
 * rotating subtitle, a step ladder (check done / spinner active / hollow
 * pending) and, under it, a caption with a clock. Extracted from the audit
 * report so agents stop re-forking this UI — same philosophy as the shared
 * split shell ([[project_split_workspace_shell]]).
 *
 * It says about time only what it knows. It used to show "~3 min" and a bar
 * that filled over 180 s on a CSS timer whatever the run was doing, so a slow
 * run read as nearly done and a fast one as stuck. The caption now counts the
 * seconds since this panel saw the work start — the same clock as the chat
 * header's status row — and there is no bar: the length of the long synthesis
 * step is not known, and a bar that guesses is what `ui/progress`'s rule
 * ("only when the fraction is real") exists to prevent.
 *
 * Two orthogonal "working" sub-states drive the visuals:
 *   - synthesising — the long analysis phase (rotating lines, spinner on the
 *     `activeId` stage). Defaults to "is the activeId step RUNNING?"; pass a
 *     bool to force it (content has no backend synth step).
 *   - writing — the final output is streaming ("writing…" on the writing
 *     stage, the streaming caption).
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
 *       RUNNING row carries `estimate` and gates the synthesising visuals.
 *   - writingId: a virtual stage that runs during `writing` (e.g. WRITE_REPORT).
 *   - synthesising / writing: see above.
 *   - lines: rotating subtitle strings shown while synthesising.
 *   - estimate: a real measure of how far the focal stage has got, when the
 *       caller has one ("4/9 categories", from the audit synthesiser). Never a
 *       guess at time: without one the row shows nothing extra and the
 *       caption's clock is the only figure.
 *   - buildingLabel / streamingLabel: the caption beside the clock.
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
  estimate,
  buildingLabel,
  streamingLabel,
  streamingSubtitle,
  idleSubtitle,
  virtualWaitsForPrior = false,
  stageChip,
}) {
  const { t } = useLingui();
  // Defaults resolved here, not in the parameter list: `t` needs the hook.
  buildingLabel ??= t`Building report`;
  streamingLabel ??= t`Generating report`;
  streamingSubtitle ??= t`Writing your report…`;
  idleSubtitle ??= t`Working on your report…`;
  // Self-driven ticker so the subtitle keeps rotating even through the long,
  // quiet stretches of synthesis when no new events arrive to re-render us.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 3000);
    return () => clearInterval(id);
  }, []);
  // Counts from mount: the panel exists only while the run does.
  const elapsed = formatElapsed(useElapsed(true));

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
      <div className="mb-8 space-y-3">
        <span className="block text-2xl font-bold tracking-tight">Duct</span>
        {/* Deliberately NOT a live region: this subtitle rotates on a timer,
            so aria-live here would interrupt a screen reader every few seconds
            with copy that carries no new information. Agent state is announced
            once, by the phase label in the chat header. */}
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
                <Spinner className="text-primary" />
              ) : status === StepStatus.SUCCESS ? (
                <Check className="size-3.5 shrink-0 text-success" aria-hidden="true" />
              ) : (
                <span className="size-3.5 shrink-0 rounded-full border border-muted-foreground/30" aria-hidden="true" />
              )}
              <span className="text-sm flex-1">{stage.label}</span>
              {running && isActive && estimate && (
                <span className="text-xs text-muted-foreground shrink-0 tabular-nums">{estimate}</span>
              )}
              {running && !isActive && stage.virtual && (
                <span className="text-xs text-muted-foreground shrink-0 animate-pulse"><Trans>writing…</Trans></span>
              )}
              {running && !isActive && !stage.virtual && (
                <span className="text-xs text-muted-foreground shrink-0 animate-pulse"><Trans>now</Trans></span>
              )}
              {stageChip ? stageChip(stage, step, status) : null}
            </div>
          );
        })}
      </div>

      {/* What is being built, and for how long. The clock is the one figure
          about the run's length this client can state rather than guess. */}
      <p className="mt-6 text-xs text-muted-foreground tabular-nums">
        {writing ? streamingLabel : buildingLabel} · {elapsed}
      </p>
    </div>
  );
}
