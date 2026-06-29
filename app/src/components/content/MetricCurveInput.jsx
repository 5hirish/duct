"use client";

import { useId, useRef } from "react";

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * Draggable retention curve. The user sweeps across the chart to trace the shape
 * they see on the platform (drag anywhere → the nearest point follows the
 * cursor), so a multi-point curve is drawn in one gesture instead of typed into
 * N boxes. Surfaces the live average + biggest drop-off, mirroring TikTok's
 * "viewers watched X%, most stopped at …" copy.
 *
 * Props:
 *   - values   : number[] (0–100), one per x-step (second for video, slide for carousel)
 *   - labels   : string[] same length — x-axis labels ("0:00" / "Slide 1")
 *   - onChange : (number[]) => void
 *   - height   : px (default 150)
 */
export default function MetricCurveInput({ values, labels, onChange, height = 150 }) {
  const gid = useId();
  const overlayRef = useRef(null);
  const dragging = useRef(false);
  const n = values.length;
  if (!n) return null;

  const xPct = (i) => (n <= 1 ? 0 : (i / (n - 1)) * 100);
  const yPct = (v) => 100 - clamp(Number(v) || 0, 0, 100); // top = 100%, bottom = 0

  function setFromEvent(e) {
    const el = overlayRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const fx = clamp((e.clientX - r.left) / r.width, 0, 1);
    const fy = clamp((e.clientY - r.top) / r.height, 0, 1);
    const idx = Math.round(fx * (n - 1));
    const val = Math.round((1 - fy) * 100);
    if (values[idx] === val) return;
    const next = values.slice();
    next[idx] = val;
    onChange(next);
  }
  const down = (e) => { dragging.current = true; e.currentTarget.setPointerCapture?.(e.pointerId); setFromEvent(e); };
  const move = (e) => { if (dragging.current) setFromEvent(e); };
  const up = (e) => { dragging.current = false; try { e.currentTarget.releasePointerCapture?.(e.pointerId); } catch { /* ignore */ } };

  const linePoints = values.map((v, i) => `${xPct(i)},${yPct(v)}`).join(" ");
  const areaPoints = `0,100 ${linePoints} 100,100`;
  const filled = values.some((v) => Number(v) > 0);
  const avg = Math.round(values.reduce((a, b) => a + (Number(b) || 0), 0) / n);

  // Biggest consecutive drop — the "where viewers leave" moment.
  let dropIdx = -1, dropAmt = 0;
  for (let i = 1; i < n; i++) {
    const d = (Number(values[i - 1]) || 0) - (Number(values[i]) || 0);
    if (d > dropAmt) { dropAmt = d; dropIdx = i; }
  }

  // A few x ticks so the axis doesn't get crowded on long curves.
  const tickIdxs = n <= 6 ? values.map((_, i) => i) : [0, Math.round((n - 1) / 2), n - 1];

  return (
    <div className="space-y-2">
      <div
        className="relative w-full select-none rounded-xl border border-border/60 bg-muted/20 px-2 pt-2"
        style={{ height }}
      >
        {/* y gridlines + labels */}
        <div className="pointer-events-none absolute inset-x-2 bottom-6 top-2 text-[9px] text-muted-foreground/60">
          {[100, 50, 0].map((g) => (
            <div key={g} className="absolute left-0 right-0 flex items-center gap-1" style={{ top: `${100 - g}%` }}>
              <span className="-translate-y-1/2 tabular-nums">{g}</span>
              <div className="h-px flex-1 border-t border-dashed border-border/50" />
            </div>
          ))}
        </div>

        {/* plot area */}
        <div className="absolute inset-x-2 bottom-6 top-2">
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full overflow-visible text-primary"
          >
            <defs>
              <linearGradient id={`rc-${gid}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="currentColor" stopOpacity="0.32" />
                <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
              </linearGradient>
            </defs>
            {filled && <polygon points={areaPoints} fill={`url(#rc-${gid})`} />}
            <polyline
              points={linePoints}
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>

          {/* handles (visual only — the overlay owns the drag) */}
          {values.map((v, i) => (
            <span
              key={i}
              className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-primary shadow-sm"
              style={{ left: `${xPct(i)}%`, top: `${yPct(v)}%` }}
            />
          ))}

          {/* drag surface */}
          <div
            ref={overlayRef}
            onPointerDown={down}
            onPointerMove={move}
            onPointerUp={up}
            onPointerCancel={up}
            className="absolute inset-0 cursor-crosshair"
            style={{ touchAction: "none" }}
          />
        </div>

        {/* x labels */}
        <div className="absolute inset-x-2 bottom-1 flex justify-between text-[9px] text-muted-foreground/70">
          {tickIdxs.map((i) => <span key={i}>{labels[i]}</span>)}
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground">
        Drag across the chart to trace your curve.
        {filled && <> <span className="font-medium text-foreground">Avg {avg}%</span></>}
        {filled && dropIdx > 0 && dropAmt >= 15 && (
          <> · biggest drop at <span className="font-medium text-foreground">{labels[dropIdx]}</span></>
        )}
        {filled && (
          <> · <button type="button" onClick={() => onChange(values.map(() => 0))} className="text-primary hover:underline">clear</button></>
        )}
      </p>
    </div>
  );
}
