import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../lib/tokens.js";
import { buildIn, springAt } from "../lib/motion.js";
import { AppShell, PaneHead } from "../ui/AppShell.jsx";
import { COMPANY, MEMORY } from "../story.js";

const ROWS = [
  { when: "12 Sep", kind: "watch · proposed", title: MEMORY.clarity.title, body: MEMORY.clarity.body },
  { when: "2 Sep", kind: "event", title: MEMORY.android.title, body: MEMORY.android.body },
  { when: "21 Aug", kind: "rule · pinned", title: MEMORY.cpa.title, body: MEMORY.cpa.body.replace("Set by Maya on 21 Aug.", "Set by Maya.") },
];

const Row = ({ when, kind, title, body, style, dot = C.hint, cardStyle, kindColor = C.hint }) => (
  <div style={{ display: "flex", gap: 16, alignItems: "flex-start", ...style }}>
    <span style={{ width: 72, fontSize: 12, color: C.muted, paddingTop: 3, flexShrink: 0 }}>{when}</span>
    <span style={{ width: 10, height: 10, borderRadius: "50%", background: dot, marginTop: 6, flexShrink: 0 }} />
    <div style={{ flexGrow: 1, background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: "12px 14px", ...cardStyle }}>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: kindColor, marginBottom: 4 }}>{kind}</div>
      <div style={{ fontSize: 14, fontWeight: 500, lineHeight: 1.3 }}>{title}</div>
      <div style={{ fontSize: 12, color: C.muted, marginTop: 4, lineHeight: 1.45 }}>{body}</div>
    </div>
  </div>
);

// 19–22 s. The camera lands on Memory. The rows it already had build in;
// the new one stamps down (1.3→1) with a two-frame ink bleed.
export const Scene5Remembers = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const T_STAMP = 22;
  const stamp = springAt(frame, fps, T_STAMP, { damping: 13, stiffness: 220 });
  const bleed = interpolate(frame, [T_STAMP + 4, T_STAMP + 6, T_STAMP + 14], [0, 0.35, 0.12], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AppShell active="Memory">
      <div style={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
        <PaneHead>Memory · what Duct knows about {COMPANY}</PaneHead>
        <div style={{ display: "flex", flexDirection: "column", gap: 18, padding: "28px 32px", maxWidth: 760 }}>
          <Row
            when="15 Sep"
            kind="learned · just now"
            kindColor={C.orange}
            dot={C.orange}
            title={MEMORY.brief.title}
            body={`From this week's signups brief: PMax signups had 7-day retention of 31% vs 54% organic. PMax · Freelancers paused on 15 Sep.`}
            style={{ opacity: Math.min(1, stamp * 3), transform: `scale(${1.3 - 0.3 * Math.min(stamp, 1)})`, transformOrigin: "left center" }}
            cardStyle={{ borderColor: C.orange, boxShadow: `0 0 0 ${4 + 6 * bleed}px rgba(255,92,0,${bleed})` }}
          />
          {ROWS.map((r, i) => (
            <Row key={r.when} {...r} style={buildIn(frame, fps, 4 + i * 4, { rise: 12 })} />
          ))}
        </div>
      </div>
    </AppShell>
  );
};
