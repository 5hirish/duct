"use client";

// The design system, rendered.
//
// Creative decisions start from the palette, and the palette was only readable
// as 70 lines of `oklch()` in tokens.css — a notation nobody can see. Worse, it
// is written twice, once for light and once for `.dark`, and the only way to
// know a dark override was missed was to notice the screen looked wrong.
//
// Everything here is read from computed style at runtime, so it cannot drift
// from tokens.css: a token added there shows up here, and the value shown is
// the one after the cascade — which is the whole point of viewing it in the
// dark frame.
//
// It is a scene like any other, so the lenses apply: the palette under
// `vision=deuteranopia` is the fastest way to find a pair that only differs by
// hue. Contrast ratios stay true under that lens, because contrast is a
// luminance ratio and hue does not enter it — the swatch changes, the number
// does not, and that disagreement is exactly the thing worth seeing.

import { useEffect, useState } from "react";

import { contrastRatio } from "./inspect";

/** The declared foreground/background contracts. Each must clear AA on its own. */
const PAIRS = [
  ["--background", "--foreground", "Page"],
  ["--card", "--card-foreground", "Card"],
  ["--popover", "--popover-foreground", "Popover"],
  ["--primary", "--primary-foreground", "Primary"],
  ["--secondary", "--secondary-foreground", "Secondary"],
  ["--muted", "--muted-foreground", "Muted"],
  ["--accent", "--accent-foreground", "Accent"],
  ["--destructive", "--destructive-foreground", "Destructive"],
  ["--success", "--success-foreground", "Success"],
  ["--warning", "--warning-foreground", "Warning"],
  ["--sidebar", "--sidebar-foreground", "Sidebar"],
];

/**
 * Colours used as ink directly on the page.
 *
 * This is the set that actually fails. A status token is picked as a dot —
 * where 3:1 against the surface is the bar — and then reused as label text,
 * where it needs 4.5:1. DESIGN.md records exactly that trap for the brand
 * orange; this table is so the next one is found before it ships.
 */
const INK = [
  "--foreground",
  "--muted-foreground",
  "--primary",
  "--destructive",
  "--success",
  "--warning",
  "--orange",
];

/** Shapes and edges, which are as much of the system as the colours. */
const SHAPE = ["--radius", "--r", "--r-lg", "--pill", "--measure", "--measure-tight"];

const SERIES = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5"];

/**
 * The two-size ladder DESIGN.md mandates, written out so a proposed third size
 * has to be added here — where it is obviously a third size — before it can be
 * added to a stylesheet, where it looks like a local decision.
 */
const LADDER = [
  { px: 16, weight: 500, tone: "", role: "Title", use: "Dialog and page titles" },
  { px: 14, weight: 600, tone: "", role: "Section", use: "Section headings" },
  { px: 14, weight: 500, tone: "", role: "Item", use: "Item and field labels" },
  { px: 14, weight: 400, tone: "muted", role: "Body", use: "Sentences the reader reads" },
  { px: 12, weight: 600, tone: "muted", role: "Micro", use: "Uppercase micro labels" },
  { px: 12, weight: 400, tone: "muted", role: "Note", use: "Hints and explanations" },
];

/**
 * Re-read on every change to <html>.
 *
 * The theme arrives as a class written by an effect, and the lenses as inline
 * style, both after this component's first paint. Observing the element is
 * shorter than guessing at an ordering and being subtly wrong once a frame.
 */
function useComputedRoot() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const ob = new MutationObserver(() => setTick((n) => n + 1));
    ob.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] });
    setTick((n) => n + 1);
    return () => ob.disconnect();
  }, []);
  return tick;
}

function value(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * The pass/fail chip.
 *
 * It carries its own background rather than tinting whatever it lands on,
 * because half of these sit on a saturated swatch: `bg-success/15` over
 * `--destructive` is a green film on red, and the first render of this sheet
 * had a verdict nobody could read on the two cards that most needed reading.
 * `--background` is the one surface every token here is already measured
 * against, so the chip is legible on all of them by construction.
 *
 * "AA"/"fail" is the non-colour channel — the chip still says which it is under
 * the greyscale lens, and under the greyscale lens is where it gets checked.
 */
function Verdict({ ratio, needs }) {
  const pass = ratio >= needs;
  return (
    <span
      className={`shrink-0 rounded-full bg-background px-1.5 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-foreground/10 ${
        pass ? "text-success" : "text-destructive"
      }`}
      title={`${ratio}:1 — needs ${needs}:1`}
    >
      {ratio} {pass ? "AA" : "fail"}
    </span>
  );
}

function Section({ title, note, children }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {note && <p className="max-w-[68ch] text-xs text-muted-foreground">{note}</p>}
      {children}
    </section>
  );
}

export default function TokenSheet() {
  const tick = useComputedRoot();
  const [rows, setRows] = useState(null);

  useEffect(() => {
    if (!tick) return;
    setRows({
      pairs: PAIRS.map(([bg, fg, label]) => ({
        label,
        bg,
        fg,
        ratio: contrastRatio(value(fg), value(bg)),
      })),
      ink: INK.map((name) => ({
        name,
        value: value(name),
        ratio: contrastRatio(value(name), value("--background")),
      })),
      shape: SHAPE.map((name) => ({ name, value: value(name) })),
    });
  }, [tick]);

  return (
    <div className="flex flex-col gap-7">
      <Section
        title="Surface pairs"
        note="Each token pair is a promise that its foreground is readable on its background. Body text needs 4.5:1."
      >
        <div className="grid gap-2 @md:grid-cols-2 @2xl:grid-cols-3">
          {(rows?.pairs || PAIRS.map(([bg, fg, label]) => ({ label, bg, fg }))).map((p) => (
            <div
              key={p.label}
              className="flex items-center justify-between gap-3 rounded-xl border p-3"
              style={{ background: `var(${p.bg})`, color: `var(${p.fg})` }}
            >
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-medium">{p.label}</span>
                <span className="text-xs opacity-70">{p.bg}</span>
              </span>
              {p.ratio != null && <Verdict ratio={p.ratio} needs={4.5} />}
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Ink on the page"
        note="The same colours used as text rather than as a dot. A 3:1 status colour is legal as a shape and illegal as a sentence — this is where that gets caught."
      >
        <div className="flex flex-col divide-y rounded-xl border">
          {(rows?.ink || []).map((i) => (
            <div key={i.name} className="flex items-center gap-3 p-2.5">
              <span
                aria-hidden="true"
                className="size-5 shrink-0 rounded-full border"
                style={{ background: `var(${i.name})` }}
              />
              <span className="text-sm font-medium" style={{ color: `var(${i.name})` }}>
                {i.name}
              </span>
              <span className="ml-auto font-mono text-xs text-muted-foreground">{i.value}</span>
              <Verdict ratio={i.ratio} needs={4.5} />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Series" note="Chart colours, which are compared to each other rather than read.">
        <div className="flex flex-wrap gap-2">
          {SERIES.map((name) => (
            <span key={name} className="flex items-center gap-2 rounded-full border py-1 pr-3 pl-1">
              <span
                aria-hidden="true"
                className="size-6 rounded-full"
                style={{ background: `var(${name})` }}
              />
              <span className="text-xs text-muted-foreground">{name.replace("--chart-", "")}</span>
            </span>
          ))}
        </div>
      </Section>

      <Section title="Type ladder" note="Three sizes. Hierarchy is carried by weight and colour, not by more sizes.">
        <div className="flex flex-col divide-y rounded-xl border">
          {LADDER.map((l) => (
            <div key={l.role} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 p-2.5">
              <span
                className={l.tone === "muted" ? "text-muted-foreground" : ""}
                style={{ fontSize: l.px, fontWeight: l.weight }}
              >
                {l.role}
              </span>
              <span className="text-xs text-muted-foreground">{l.use}</span>
              <span className="ml-auto font-mono text-xs text-muted-foreground tabular-nums">
                {l.px}/{l.weight}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Shape" note="Radii and the reading measure, in the units they are declared in.">
        <div className="flex flex-wrap gap-2">
          {(rows?.shape || []).map((s) => (
            <span key={s.name} className="rounded-lg border px-2.5 py-1.5 text-xs">
              <span className="font-medium">{s.name}</span>{" "}
              <span className="font-mono text-muted-foreground">{s.value}</span>
            </span>
          ))}
        </div>
      </Section>
    </div>
  );
}
