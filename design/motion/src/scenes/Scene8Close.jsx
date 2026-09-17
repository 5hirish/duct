import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "../lib/tokens.js";
import { buildIn, springAt } from "../lib/motion.js";
import { Wordmark } from "../ui/bits.jsx";
import { OpenAiMark } from "../ui/OpenAiMark.jsx";

// 28–30 s. Hard cut to navy. Two lines, the one thing to remember, two
// buttons. The palette blend happens in the Film's Ground, not here.
export const Scene8Close = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const line1 = buildIn(frame, fps, 4, { rise: 24 });
  const line2 = buildIn(frame, fps, 14, { rise: 24 });
  const pillP = springAt(frame, fps, 24, { damping: 9, stiffness: 150 });
  const ring = interpolate(frame, [28, 38, 52], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const buttons = buildIn(frame, fps, 36, { rise: 16 });
  return (
    <AbsoluteFill style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 40, color: C.white, fontFamily: FONT.sans }}>
      <div style={buildIn(frame, fps, 0, { rise: 10 })}>
        <Wordmark light size={28} />
      </div>

      <div style={{ textAlign: "center", fontFamily: FONT.serif, fontSize: 104, lineHeight: 1.06, letterSpacing: "-0.02em" }}>
        <div style={line1}>Open source. MIT.</div>
        <div style={line2}>
          <em style={{ color: C.orange }}>Bring your own keys.</em>
        </div>
      </div>

      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 14,
          padding: "14px 26px 14px 18px",
          borderRadius: 100,
          border: "1.5px solid rgba(255,92,0,0.7)",
          background: "rgba(255,92,0,0.10)",
          boxShadow: `0 0 0 ${8 + 14 * ring}px rgba(255,92,0,${0.08 + 0.12 * ring})`,
          fontSize: 22,
          marginTop: -8,
          opacity: Math.min(1, pillP * 2),
          transform: `scale(${pillP})`,
        }}
      >
        <span style={{ width: 40, height: 40, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <OpenAiMark size={30} fill={C.white} />
        </span>
        <span>
          or the <strong>ChatGPT subscription</strong> you already pay for
        </span>
        <span style={{ fontSize: 14, color: C.navy3, paddingLeft: 6, borderLeft: "1px solid rgba(255,255,255,0.2)" }}>no API key needed</span>
      </div>

      <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 8, ...buttons }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 10, padding: "18px 30px", borderRadius: 100, background: C.orange, color: C.white, fontSize: 20, fontWeight: 600 }}>
          Download for macOS
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12M6 11l6 6 6-6M5 21h14" /></svg>
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 10, padding: "18px 30px", borderRadius: 100, border: "1.5px solid rgba(255,255,255,0.35)", color: C.white, fontSize: 20, fontWeight: 500 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9L12 3z" /></svg>
          Star on GitHub
        </span>
      </div>

      <div style={{ fontSize: 18, color: C.navy3, ...buttons }}>Free, on your Mac. Windows and Linux too.</div>
    </AbsoluteFill>
  );
};
