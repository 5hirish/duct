import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "../lib/tokens.js";
import { buildIn, countUp, ease, openFrom, springAt, typed, typedDuration } from "../lib/motion.js";
import { AppShell, PaneHead } from "../ui/AppShell.jsx";
import { Mark } from "../ui/bits.jsx";
import { N, QUESTION, WEEK_SHORT } from "../story.js";

const T_TYPED = typedDuration(QUESTION); // ~60 frames
const T_PILL = T_TYPED + 8;
const T_CHIPS = T_PILL + 14;
const T_FIND = T_CHIPS + 20;
const T_LINE = T_FIND + 18;
const T_UNDER = T_LINE + 14;

const CHIPS = [
  { id: "google-ads", label: "Ads", value: 3, format: (v) => `${Math.round(v)} campaigns` },
  { id: "googleanalytics", label: "GA4", value: N.signups, format: (v) => `${Math.round(v)} signups` },
  { id: "stripe", label: "Stripe", value: 18400, format: (v) => `€${Math.round(v).toLocaleString("en-GB")} MRR` },
];

const Finding = ({ frame, fps, delay, title, tone, sub }) => {
  const p = springAt(frame, fps, delay, { damping: 11, stiffness: 140 });
  return (
    <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: "16px 18px", flex: 1, opacity: Math.min(1, p * 2), transform: `scale(${0.9 + 0.1 * p})` }}>
      <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: "-0.02em", color: tone, lineHeight: 1.15 }}>{title}</div>
      <div style={{ fontSize: 12, color: C.muted, marginTop: 6 }}>{sub}</div>
    </div>
  );
};

// 9–14 s. The question is typed with human cadence; the latency pill says
// what is being read; three chips land together with live counters; two
// findings overshoot in; the sentence lands; the underline draws.
export const Scene3Reads = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const q = typed(QUESTION, frame, 4);
  const pill = openFrom(frame, fps, T_PILL, "left center");
  const chips = buildIn(frame, fps, T_CHIPS, { rise: 10 });
  const line = buildIn(frame, fps, T_LINE, { rise: 8 });
  const underline = ease(frame, T_UNDER, 14);
  return (
    <AppShell active="Insights">
      <div style={{ width: 600, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column", boxSizing: "border-box" }}>
        <PaneHead>Insights · {WEEK_SHORT}</PaneHead>
        <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 24, flexGrow: 1 }}>
          <div style={{ alignSelf: "flex-end", maxWidth: "88%", background: C.surface, borderRadius: "10px 4px 10px 10px", padding: "10px 14px", fontSize: 15, lineHeight: 1.5, minHeight: 22, opacity: frame >= 4 ? 1 : 0 }}>
            {q.shown}
            {q.done ? null : <span style={{ opacity: frame % 16 < 8 ? 1 : 0 }}>▌</span>}
          </div>

          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, alignSelf: "flex-start", padding: "6px 12px", borderRadius: 999, border: `1px solid ${C.border}`, background: C.white, fontSize: 13, color: C.muted, ...pill }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: C.orange, opacity: 0.5 + 0.5 * Math.abs(Math.sin(frame / 6)) }} />
            reading <strong style={{ color: C.ink, fontWeight: 500 }}>Ads · GA4 · Stripe</strong>
          </div>

          <div style={{ display: "flex", gap: 8, ...chips }}>
            {CHIPS.map((c) => (
              <span key={c.id} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 999, border: `1px solid ${C.border}`, background: C.white, fontSize: 12 }}>
                <Mark id={c.id} size={14} />
                <span style={{ fontWeight: 500 }}>{c.label}</span>
                <span style={{ fontFamily: FONT.mono, fontSize: 11, color: C.muted }}>{countUp(frame, T_CHIPS + 4, 22, c.value, c.format)}</span>
              </span>
            ))}
          </div>

          <div style={{ display: "flex", gap: 12 }}>
            <Finding frame={frame} fps={fps} delay={T_FIND} title={`ROAS ↑ ${N.roasDelta.replace("+", "")}`} tone={C.success} sub="almost all from Performance Max" />
            <Finding frame={frame} fps={fps} delay={T_FIND + 5} title={`Android D7 ↓ ${N.androidRetentionDrop}`} tone={C.destructive} sub="PMax cohort vs organic, 31% vs 54%" />
          </div>

          <div style={{ fontSize: 15, lineHeight: 1.55, ...line }}>
            Performance Max is buying signups at <strong>€{N.pmaxCpa.toFixed(2)}</strong> against a <strong>€12</strong> target, and its Android users leave within a week.{" "}
            <span style={{ position: "relative", fontWeight: 500 }}>
              You're paying to acquire churners.
              <span style={{ position: "absolute", left: 0, bottom: -3, height: 2.5, width: `${underline * 100}%`, background: C.orange, borderRadius: 2 }} />
            </span>
          </div>
        </div>
      </div>

      <div style={{ flexGrow: 1, display: "flex", flexDirection: "column", background: C.paper }}>
        <PaneHead>Brief</PaneHead>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 28, color: C.hint, fontSize: 14 }}>
          {[70, 90, 60].map((w, i) => (
            <div key={w} style={{ height: i === 0 ? 22 : 14, width: `${w}%`, borderRadius: 6, background: C.surface, opacity: ease(frame, T_PILL + i * 6, 10) }} />
          ))}
          <div style={{ marginTop: 8, opacity: ease(frame, T_CHIPS, 10) }}>writing…</div>
        </div>
      </div>
    </AppShell>
  );
};
