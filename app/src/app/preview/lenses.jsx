"use client";

// Lenses — the same scene, seen under a different condition.
//
// A device and a theme change what the component *is*; a lens changes who is
// looking at it. Both are review axes, and the second one is the one that gets
// skipped, because nothing on a designer's machine simulates it by default.
//
// Each lens is a URL parameter on /preview/frame, so a state is reachable
// without clicking: ?vision=deuteranopia&text=125&inspect=grid.
//
// Kept in one module because the shell renders the pickers and the frame
// applies the effect; two copies of this list would drift the moment one grew
// an option.

/**
 * Colour-vision simulation.
 *
 * DESIGN.md and WCAG 1.4.1 both say colour is never the only channel, and this
 * codebase leans on colour constantly — a green/amber/grey status dot, a tinted
 * destructive button, chart series. That rule is cheap to write and easy to
 * believe you have followed. Under `deuteranopia` the connector tile's green
 * "connected" dot and its amber "partial" dot converge, which is exactly why
 * the word stays next to the dot.
 *
 * Matrices are the Viénot/Brettel approximations every simulator ships. They
 * are an approximation of a spectrum, not a diagnosis — the question they
 * answer is "does this still parse when the hue difference goes away", and for
 * that they are sufficient.
 */
export const VISION = [
  { id: "normal", label: "Normal", matrix: null },
  {
    id: "protanopia",
    label: "Protanopia",
    note: "No long-wave (red) cones — about 1% of men.",
    matrix: "0.567 0.433 0 0 0  0.558 0.442 0 0 0  0 0.242 0.758 0 0  0 0 0 1 0",
  },
  {
    id: "deuteranopia",
    label: "Deuteranopia",
    note: "No medium-wave (green) cones. The most common form, ~6% of men.",
    matrix: "0.625 0.375 0 0 0  0.70 0.30 0 0 0  0 0.30 0.70 0 0  0 0 0 1 0",
  },
  {
    id: "tritanopia",
    label: "Tritanopia",
    note: "No short-wave (blue) cones. Rare, and brutal on blue/green pairs.",
    matrix: "0.95 0.05 0 0 0  0 0.433 0.567 0 0  0 0.475 0.525 0 0  0 0 0 1 0",
  },
  {
    id: "greyscale",
    label: "Greyscale",
    note: "No hue at all — also the printout, and the screenshot in a doc.",
    matrix: "0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0.299 0.587 0.114 0 0  0 0 0 1 0",
  },
];

/**
 * Reader text size.
 *
 * AGENTS.md requires type, spacing and sticky offsets in `rem` precisely so
 * they follow the reader's setting — which means the rule is only worth
 * anything if someone occasionally moves the setting. A layout that survives
 * 100% and collapses at 150% has a `px` in it somewhere, and this is how that
 * shows up as a picture rather than as a grep.
 *
 * 200% is the WCAG 1.4.4 requirement; 150% is where our densest rows start to
 * argue with each other, so it is the more useful default to check.
 */
export const TEXT_SCALES = [
  { id: "100", label: "100%", px: 16 },
  { id: "125", label: "125%", px: 20 },
  { id: "150", label: "150%", px: 24 },
  { id: "200", label: "200%", px: 32 },
];

/** Debug paint. `grid` is the rhythm check; the other two are box geometry. */
export const OVERLAYS = [
  { id: "off", label: "None" },
  { id: "outline", label: "Outline" },
  { id: "spacing", label: "Spacing" },
  { id: "grid", label: "8px grid" },
];

export const DEFAULT_LENSES = { vision: "normal", text: "100", inspect: "off" };

export function textScalePx(id) {
  return (TEXT_SCALES.find((t) => t.id === id) || TEXT_SCALES[0]).px;
}

export function visionFilter(id) {
  const lens = VISION.find((v) => v.id === id);
  return lens && lens.matrix ? `url(#pv-${lens.id})` : "";
}

/**
 * The filter definitions themselves, mounted once per frame document.
 *
 * `color-interpolation-filters="sRGB"` is not optional: SVG filters default to
 * linearRGB, and these matrices are published for sRGB. Left on the default the
 * simulation is still a picture of *something*, just not of the deficiency —
 * the failure mode where the tool quietly lies is the one worth spending a line
 * of markup on.
 */
export function VisionFilters() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width="0"
      height="0"
      style={{ position: "absolute", width: 0, height: 0, overflow: "hidden" }}
    >
      <defs>
        {VISION.filter((v) => v.matrix).map((v) => (
          <filter key={v.id} id={`pv-${v.id}`} colorInterpolationFilters="sRGB">
            <feColorMatrix type="matrix" values={v.matrix} />
          </filter>
        ))}
      </defs>
    </svg>
  );
}
