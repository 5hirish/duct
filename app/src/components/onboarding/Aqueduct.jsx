"use client";

// The onboarding flow is one aqueduct. A channel runs along the top, one
// arch per step underneath, and water — the only blue on the page, the same
// rule the mosaic panels keep — advances through the channel as each step
// completes. The crawl is literally water moving while the user is on the
// provider step; skip without a key and the channel stops dry at the second
// arch, which is the whole explanation of why the audit cannot run yet.
//
// It replaces a percentage bar because a percentage measures the user's
// remaining labour; this measures how far the data has got.
//
// The SVG is decorative and the list beneath it is the accessible truth: each
// step's label and state are real text, and the current one carries
// aria-current.

import { cn } from "@/lib/utils";

export const STEP_DONE = "done";
export const STEP_ACTIVE = "active";
export const STEP_TODO = "todo";
// The channel ran dry here — a step that was skipped rather than finished.
export const STEP_DRY = "dry";

const WIDTH = 640;
const CHANNEL_Y = 14;
const CHANNEL_H = 22;
const PIER_W = 22;
const ARCH_TOP = 50;
const GROUND_Y = 124;
// Courses of masonry across the piers and spandrels — the texture that makes
// the strip read as stone rather than as a progress bar in disguise.
const COURSE_H = 12;

/**
 * @param {{ key: string, label: string, state: string }[]} steps
 * @param {number} water — how far the water has got, in steps (0…steps.length,
 *   fractions allowed while a step is in progress)
 */
export default function Aqueduct({ steps, water = 0, className }) {
  const n = Math.max(steps.length, 1);
  const seg = WIDTH / n;
  const reach = Math.max(0, Math.min(water, n)) / n;
  const waterWidth = Math.round((WIDTH - 6) * reach);
  const dryAt = steps.findIndex((s) => s.state === STEP_DRY);
  const flowing = reach > 0 && reach < 1;

  return (
    <div className={cn("aqueduct", flowing && "aqueduct-flowing", className)}>
      <svg
        viewBox={`0 0 ${WIDTH} ${GROUND_Y + 6}`}
        className="aqueduct-svg"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <pattern id="aq-courses" width="40" height={COURSE_H} patternUnits="userSpaceOnUse">
            <rect width="40" height={COURSE_H} className="aqueduct-stone" />
            <path d={`M0 ${COURSE_H - 0.5} H40 M20 0 V${COURSE_H}`} className="aqueduct-joint" />
          </pattern>
          <clipPath id="aq-channel">
            <rect x="3" y={CHANNEL_Y + 5} width={WIDTH - 6} height={CHANNEL_H - 10} rx="2" />
          </clipPath>
        </defs>

        {/* the spandrel wall: masonry, with the arches cut out of it */}
        <rect x="0" y={CHANNEL_Y + CHANNEL_H} width={WIDTH} height={GROUND_Y - CHANNEL_Y - CHANNEL_H} fill="url(#aq-courses)" />
        {steps.map((step, i) => {
          const x0 = i * seg + PIER_W;
          const x1 = (i + 1) * seg - PIER_W;
          const r = (x1 - x0) / 2;
          return (
            <path
              key={`cut-${step.key}`}
              d={`M ${x0} ${GROUND_Y + 6} V ${ARCH_TOP + r} A ${r} ${r} 0 0 1 ${x1} ${ARCH_TOP + r} V ${GROUND_Y + 6} Z`}
              className="aqueduct-void"
            />
          );
        })}
        {/* the voussoirs — the arch ring, ochre, brighter on the live step */}
        {steps.map((step, i) => {
          const x0 = i * seg + PIER_W;
          const x1 = (i + 1) * seg - PIER_W;
          const r = (x1 - x0) / 2;
          return (
            <path
              key={step.key}
              d={`M ${x0} ${GROUND_Y} V ${ARCH_TOP + r} A ${r} ${r} 0 0 1 ${x1} ${ARCH_TOP + r} V ${GROUND_Y}`}
              className={cn(
                "aqueduct-arch",
                step.state === STEP_ACTIVE && "aqueduct-arch-active",
                step.state === STEP_DONE && "aqueduct-arch-done",
              )}
            />
          );
        })}

        {/* the channel (specus): a stone trough with the water inside it */}
        <rect x="0" y={CHANNEL_Y} width={WIDTH} height={CHANNEL_H} rx="3" className="aqueduct-stone" />
        <rect x="3" y={CHANNEL_Y + 5} width={WIDTH - 6} height={CHANNEL_H - 10} rx="2" className="aqueduct-bed" />
        <g clipPath="url(#aq-channel)">
          <rect x="3" y={CHANNEL_Y + 5} width={waterWidth} height={CHANNEL_H - 10} className="aqueduct-water" />
          {/* light on the surface, drifting with the current */}
          <rect x="3" y={CHANNEL_Y + 5} width={waterWidth} height="3" className="aqueduct-glint" />
        </g>
        {dryAt >= 0 && (
          // One terracotta tessera where the water stopped — the consequence
          // colour, under 8% of the tiles, exactly as the mosaic rule says.
          <rect
            x={dryAt * seg + seg / 2 - 7}
            y={CHANNEL_Y + 4}
            width="14"
            height="14"
            rx="1"
            className="aqueduct-dry"
          />
        )}
        <rect x="0" y={GROUND_Y} width={WIDTH} height="6" className="aqueduct-ground" />
      </svg>
      <ol className="aqueduct-steps" aria-label="Setup steps">
        {steps.map((step, i) => (
          <li
            key={step.key}
            className={cn("aqueduct-step", `aqueduct-step-${step.state}`)}
            aria-current={step.state === STEP_ACTIVE ? "step" : undefined}
          >
            <span className="aqueduct-step-index" aria-hidden="true">
              {["I", "II", "III", "IV", "V"][i] || i + 1}
            </span>
            <span className="aqueduct-step-label">{step.label}</span>
            <span className="sr-only">
              {step.state === STEP_DONE && " — done"}
              {step.state === STEP_ACTIVE && " — current step"}
              {step.state === STEP_DRY && " — skipped"}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
